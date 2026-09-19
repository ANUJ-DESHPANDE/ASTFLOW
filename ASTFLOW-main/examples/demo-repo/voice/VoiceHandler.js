import { normalizeInput } from './normalizeInput.js';
import { IntentRouter } from './IntentRouter.js';

export class VoiceHandler {
  constructor() { this.router = new IntentRouter(); }
  /** Clean a spoken command before routing it to the device agent. */
  handle(raw) {
    const input = normalizeInput(raw);
    return this.handleRequest(input);
  }
  handleRequest(input) { return this.router.route(input); }
}
