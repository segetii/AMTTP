/**
 * Base service class for all AMTTP services
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
export declare abstract class BaseService {
    protected readonly http: AxiosInstance;
    protected readonly events: EventEmitter;
    constructor(http: AxiosInstance, events: EventEmitter);
}
//# sourceMappingURL=base.d.ts.map