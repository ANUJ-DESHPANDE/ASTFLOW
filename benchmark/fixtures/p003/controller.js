import { placeOrder } from './service.js';

export function handleOrder(request) {
  return placeOrder(request.id);
}
