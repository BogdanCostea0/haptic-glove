#include "BLETransport.h"
#include "Protocol.h"

// ── RX characteristic callback ────────────────────────────────────────────────
class RxCallback : public BLECharacteristicCallbacks {
public:
    explicit RxCallback(BLETransport::CommandCallback cb) : _cb(cb) {}
    void onWrite(BLECharacteristic* c) override {
        if (_cb) _cb(c->getValue());
    }
private:
    BLETransport::CommandCallback _cb;
};

// ── BLETransport ──────────────────────────────────────────────────────────────
void BLETransport::begin(const char* deviceName) {
    BLEDevice::init(deviceName);

    _server = BLEDevice::createServer();
    _server->setCallbacks(this);

    BLEService* service = _server->createService(NUS_SERVICE_UUID);

    // TX: ESP32 notifies the host with sensor packets
    _txChar = service->createCharacteristic(NUS_TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    _txChar->addDescriptor(new BLE2902());

    // RX: host writes commands (e.g. haptic triggers) to the ESP32
    BLECharacteristic* rxChar = service->createCharacteristic(
        NUS_RX_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
    );
    rxChar->setCallbacks(new RxCallback(_cmdCb));

    service->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(NUS_SERVICE_UUID);
    adv->setScanResponse(true);
    BLEDevice::startAdvertising();
}

void BLETransport::send(const GloveState& state) {
    if (!_connected) return;
    String packet = serializeState(state);
    packet += '\n';
    _txChar->setValue(std::string(packet.c_str()));  // use string overload — avoids const uint8_t* mismatch
    _txChar->notify();
}

void BLETransport::onConnect(BLEServer*) {
    _connected = true;
}

void BLETransport::onDisconnect(BLEServer*) {
    _connected = false;
    BLEDevice::startAdvertising();  // resume advertising so host can reconnect
}
