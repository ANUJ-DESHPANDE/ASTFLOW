import { handleOrder } from './controller.js';

export function startOrder(request) {
  return handleOrder(request);
}
