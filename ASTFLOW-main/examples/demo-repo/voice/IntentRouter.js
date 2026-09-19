import { BluetoothAgent } from '../bluetooth/BluetoothAgent.js';
import { openWifiSettings } from '../settings/deeplinks.js';

export class IntentRouter {
  constructor() { this.bluetooth = new BluetoothAgent(); }
  /** Route a voice request to a device agent or wireless network settings. */
  route(input) {
    if (input.includes('bluetooth')) return this.bluetooth.execute();
    if (input.includes('wifi')) return openWifiSettings();
    return { status: 'unknown_intent' };
  }
}
