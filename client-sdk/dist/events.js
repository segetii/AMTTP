"use strict";
/**
 * Simple Event Emitter for AMTTP SDK
 * Provides typed event handling
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.EventEmitter = void 0;
const eventemitter3_1 = __importDefault(require("eventemitter3"));
class EventEmitter extends eventemitter3_1.default {
    /**
     * Wait for a specific event with timeout
     */
    waitFor(event, timeout = 30000) {
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                reject(new Error(`Timeout waiting for event: ${String(event)}`));
            }, timeout);
            this.once(event, ((...args) => {
                clearTimeout(timer);
                resolve(args);
            }));
        });
    }
    /**
     * Emit with logging
     */
    emitWithLog(event, ...args) {
        if (process.env.AMTTP_DEBUG) {
            console.log(`[AMTTP Event] ${String(event)}:`, ...args);
        }
        return this.emit(event, ...args);
    }
}
exports.EventEmitter = EventEmitter;
//# sourceMappingURL=events.js.map