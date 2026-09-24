import { checkBluetoothPermission } from './permissions.js';
import { openBluetoothSettings } from '../settings/deeplinks.js';

export class BluetoothAgent {
  /** Handle a request to open Bluetooth settings after checking permission. */
  execute() {
    checkBluetoothPermission();
    return openBluetoothSettings();
  }
}
