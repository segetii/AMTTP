declare module 'snarkjs' {
  export interface Groth16Proof {
    pi_a: string[];
    pi_b: string[][];
    pi_c: string[];
    protocol: string;
    curve: string;
    [key: string]: unknown;
  }

  export const groth16: {
    fullProve(
      input: Record<string, unknown>,
      wasmFile: string,
      zkeyFile: string
    ): Promise<{ proof: Groth16Proof; publicSignals: string[] }>;
    verify(
      vkey: unknown,
      publicSignals: string[],
      proof: unknown
    ): Promise<boolean>;
    exportSolidityCallData(
      proof: unknown,
      publicSignals: string[]
    ): Promise<string>;
  };
  export const zKey: {
    exportVerificationKey(zkeyFile: string): Promise<unknown>;
  };
}
