/*
 * AMTTP zkNAF - Risk Score Range Proof
 * 
 * Proves that a user's risk score falls within a specific range without
 * revealing the exact score.
 * 
 * Ranges:
 *   - LOW: 0-39 (transactions can proceed)
 *   - MEDIUM: 40-69 (may require additional verification)
 *   - HIGH: 70-100 (blocked, requires review)
 * 
 * FCA COMPLIANCE NOTE:
 * This proof is for PUBLIC verification. The exact risk score, contributing
 * factors, and XAI explanation are maintained by the regulated entity for
 * regulatory disclosure under MLR 2017.
 * 
 * Circuit: Range proof using comparators
 * - Public Input: Oracle signature commitment, range bounds
 * - Private Input: Actual risk score, oracle signature
 * - Output: 1 if score is in range, 0 otherwise
 */

pragma circom 2.1.6;

include "node_modules/circomlib/circuits/poseidon.circom";
include "node_modules/circomlib/circuits/comparators.circom";
include "node_modules/circomlib/circuits/bitify.circom";

/*
 * RangeProof - Proves a value is within [min, max]
 */
template RangeProof(n) {
    signal input value;
    signal input minValue;
    signal input maxValue;
    signal output inRange;

    // Check value >= minValue
    component geMin = GreaterEqThan(n);
    geMin.in[0] <== value;
    geMin.in[1] <== minValue;

    // Check value <= maxValue
    component leMax = LessEqThan(n);
    leMax.in[0] <== value;
    leMax.in[1] <== maxValue;

    // Both conditions must be true
    inRange <== geMin.out * leMax.out;
}

/*
 * OracleSignatureVerifier - Verifies the risk score was signed by authorized oracle
 * Uses Poseidon hash for signature verification
 */
template OracleSignatureVerifier() {
    signal input riskScore;
    signal input userAddress;
    signal input timestamp;
    signal input oracleSecret;  // Private key component
    signal input signatureCommitment;  // Public commitment
    
    signal output isValid;

    // Compute expected commitment: H(riskScore, userAddress, timestamp, oracleSecret)
    component hasher = Poseidon(4);
    hasher.inputs[0] <== riskScore;
    hasher.inputs[1] <== userAddress;
    hasher.inputs[2] <== timestamp;
    hasher.inputs[3] <== oracleSecret;

    // Check commitment matches
    component eq = IsEqual();
    eq.in[0] <== hasher.out;
    eq.in[1] <== signatureCommitment;

    isValid <== eq.out;
}

/*
 * RiskScoreRangeProof - Main circuit for proving risk score is in a range
 * 
 * Public Inputs:
 *   - signatureCommitment: Commitment from oracle signing the score
 *   - userAddressHash: Hash of user's address (for binding)
 *   - minScore: Minimum of the range (e.g., 0 for LOW)
 *   - maxScore: Maximum of the range (e.g., 39 for LOW)
 *   - currentTimestamp: Current time
 * 
 * Private Inputs:
 *   - riskScore: The actual risk score (0-100)
 *   - userAddress: User's address
 *   - scoreTimestamp: When score was computed
 *   - oracleSecret: Oracle's signing key
 */
template RiskScoreRangeProof() {
    // Public inputs
    signal input signatureCommitment;
    signal input userAddressHash;
    signal input minScore;
    signal input maxScore;
    signal input currentTimestamp;
    
    // Private inputs
    signal input riskScore;
    signal input userAddress;
    signal input scoreTimestamp;
    signal input oracleSecret;
    
    // Outputs
    signal output isInRange;
    signal output isSignatureValid;
    signal output isNotExpired;
    
    // Step 1: Verify user address matches the hash
    component addrHasher = Poseidon(1);
    addrHasher.inputs[0] <== userAddress;
    addrHasher.out === userAddressHash;
    
    // Step 2: Verify oracle signature on the risk score
    component sigVerifier = OracleSignatureVerifier();
    sigVerifier.riskScore <== riskScore;
    sigVerifier.userAddress <== userAddress;
    sigVerifier.timestamp <== scoreTimestamp;
    sigVerifier.oracleSecret <== oracleSecret;
    sigVerifier.signatureCommitment <== signatureCommitment;
    isSignatureValid <== sigVerifier.isValid;
    
    // Step 3: Verify risk score is in range (using 8 bits for 0-100 range)
    component rangeProof = RangeProof(8);
    rangeProof.value <== riskScore;
    rangeProof.minValue <== minScore;
    rangeProof.maxValue <== maxScore;
    isInRange <== rangeProof.inRange;
    
    // Step 4: Verify score is not expired (within 24 hours = 86400 seconds)
    component notExpired = LessThan(64);
    notExpired.in[0] <== currentTimestamp - scoreTimestamp;
    notExpired.in[1] <== 86400;  // 24 hours in seconds
    isNotExpired <== notExpired.out;
    
    // All conditions must be true (handled in application logic)
}

// Export with public inputs
component main {public [signatureCommitment, userAddressHash, minScore, maxScore, currentTimestamp]} = RiskScoreRangeProof();
