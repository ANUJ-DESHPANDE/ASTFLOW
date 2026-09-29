import { saveOrder } from './repository.js';
import { normalizeOrder } from './helper.js';

export function placeOrder(id) {
  return saveOrder(normalizeOrder(id));
}

export function unusedReport() {
  return 'unused';
}
