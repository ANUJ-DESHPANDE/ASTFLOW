/** Open the Bluetooth settings panel using the settings://bluetooth deeplink. */
export function openBluetoothSettings() { return openSettingsUri('settings://bluetooth'); }
/** Configure the wireless network connection. */
export function openWifiSettings() { return openSettingsUri('settings://wifi'); }
/** Produce a settings URI for the host application. */
export function openSettingsUri(uri) { return { uri }; }
