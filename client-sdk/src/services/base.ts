/**
 * Base service class for all AMTTP services
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';

export abstract class BaseService {
  protected readonly http: AxiosInstance;
  protected readonly events: EventEmitter;

  constructor(http: AxiosInstance, events: EventEmitter) {
    this.http = http;
    this.events = events;
  }
}
