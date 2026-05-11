import json
import queue
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

import serial

from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float32MultiArray, Int32


class GloveDriverNode(Node):
    def __init__(self):
        super().__init__('glove_driver')

        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud_rate', 115200)
        self.declare_parameter('frame_id', 'glove')
        self.declare_parameter('reconnect_delay', 2.0)

        self._port_name       = self.get_parameter('port').value
        self._baud_rate       = self.get_parameter('baud_rate').value
        self._frame_id        = self.get_parameter('frame_id').value
        self._reconnect_delay = self.get_parameter('reconnect_delay').value

        # Best-effort QoS — acceptable to drop frames for real-time sensors
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self._pub_imu    = self.create_publisher(Imu,              'glove/imu',    sensor_qos)
        self._pub_flex   = self.create_publisher(Float32MultiArray, 'glove/flex',   sensor_qos)
        self._pub_button = self.create_publisher(Bool,             'glove/button', sensor_qos)

        self.create_subscription(Int32, 'glove/haptic', self._haptic_cb, 10)

        self._queue   = queue.Queue(maxsize=5)
        self._serial  = None
        self._running = True

        self._thread = threading.Thread(target=self._read_loop, daemon=True, name='GloveSerial')
        self._thread.start()

        # Drain the queue at 200 Hz; the serial thread fills it at ~50 Hz
        self.create_timer(0.005, self._publish_queued)

        self.get_logger().info(
            f'GloveDriver ready — port={self._port_name}  baud={self._baud_rate}')

    # ── Serial reader (background thread) ────────────────────────────────────

    def _read_loop(self):
        while self._running:
            try:
                self._serial = serial.Serial(self._port_name, self._baud_rate, timeout=2.0)
                self.get_logger().info(f'Connected to {self._port_name}')

                while self._running:
                    try:
                        raw = self._serial.readline()
                    except serial.SerialTimeoutException:
                        continue

                    line = raw.decode('utf-8', errors='ignore').strip()
                    if not line or line.startswith('['):
                        continue

                    try:
                        pkt = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    f = pkt.get('f')
                    q = pkt.get('q')
                    if f is None or q is None or len(f) < 4 or len(q) < 4:
                        continue

                    if self._queue.full():
                        try:
                            self._queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._queue.put_nowait({'f': f, 'q': q, 'b': pkt.get('b', 0)})

                self._serial.close()

            except serial.SerialException as e:
                self.get_logger().warn(
                    f'Serial error: {e} — retrying in {self._reconnect_delay:.0f}s')
                try:
                    self._serial and self._serial.close()
                except Exception:
                    pass
                self._serial = None
                time.sleep(self._reconnect_delay)

        self.get_logger().info('Serial reader stopped.')

    # ── Publish (main thread timer) ───────────────────────────────────────────

    def _publish_queued(self):
        while not self._queue.empty():
            try:
                pkt = self._queue.get_nowait()
            except queue.Empty:
                break

            now = self.get_clock().now().to_msg()

            # IMU — Mahony-fused orientation only.
            # Firmware sends q = [w, x, y, z]; ROS Imu uses x, y, z, w.
            imu = Imu()
            imu.header.stamp    = now
            imu.header.frame_id = self._frame_id
            imu.orientation.x   = float(pkt['q'][1])
            imu.orientation.y   = float(pkt['q'][2])
            imu.orientation.z   = float(pkt['q'][3])
            imu.orientation.w   = float(pkt['q'][0])
            imu.orientation_covariance[0]         = 0.01  # rough diagonal estimate
            imu.angular_velocity_covariance[0]    = -1.0  # not available
            imu.linear_acceleration_covariance[0] = -1.0  # not available
            self._pub_imu.publish(imu)

            # Flex — 4 angles in degrees [index, middle, ring, pinky]
            flex = Float32MultiArray()
            flex.data = [float(v) for v in pkt['f'][:4]]
            self._pub_flex.publish(flex)

            # Button
            btn = Bool()
            btn.data = bool(pkt['b'])
            self._pub_button.publish(btn)

    # ── Haptic subscriber ─────────────────────────────────────────────────────

    def _haptic_cb(self, msg: Int32):
        if self._serial and self._serial.is_open:
            try:
                self._serial.write(f'H{msg.data}\n'.encode())
            except serial.SerialException as e:
                self.get_logger().warn(f'Haptic send failed: {e}')
        else:
            self.get_logger().warn('Haptic ignored — serial not connected')

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy_node(self):
        self._running = False
        try:
            self._serial and self._serial.close()
        except Exception:
            pass
        self._thread.join(timeout=3.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GloveDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
