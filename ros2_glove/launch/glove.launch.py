from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('port',             default_value='/dev/ttyUSB0',
                              description='Serial port the ESP32 is on'),
        DeclareLaunchArgument('baud_rate',        default_value='115200'),
        DeclareLaunchArgument('frame_id',         default_value='glove',
                              description='TF frame attached to IMU messages'),
        DeclareLaunchArgument('reconnect_delay',  default_value='2.0',
                              description='Seconds to wait before re-opening port after error'),

        Node(
            package='ros2_glove',
            executable='glove_driver',
            name='glove_driver',
            output='screen',
            parameters=[{
                'port':            LaunchConfiguration('port'),
                'baud_rate':       LaunchConfiguration('baud_rate'),
                'frame_id':        LaunchConfiguration('frame_id'),
                'reconnect_delay': LaunchConfiguration('reconnect_delay'),
            }],
        ),
    ])
