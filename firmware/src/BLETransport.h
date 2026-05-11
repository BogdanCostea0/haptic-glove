#pragma once
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "GloveState.h"

// Nordic UART Service — supported natively by bleak (Python) and most BLE tools.
// Unity can receive data via the Windows BLE API or a plugin that speaks NUS.
#define NUS_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 → host
#define NUS_RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // host → ESP32

class BLETransport : public BLEServerCallbacks {
public:
    void begin(const char* deviceName = "VR-Glove");
    void send(const GloveState& state);
    bool isConnected() const { return _connected; }

    // Incoming command handler (e.g. "H1\n" to trigger haptic effect 1)
    using CommandCallback = void (*)(const std::string& cmd);
    void onCommand(CommandCallback cb) { _cmdCb = cb; }

private:
    void onConnect(BLEServer*)    override;
    void onDisconnect(BLEServer*) override;

    BLEServer*          _server    = nullptr;
    BLECharacteristic*  _txChar    = nullptr;
    bool                _connected = false;
    CommandCallback     _cmdCb     = nullptr;
};
