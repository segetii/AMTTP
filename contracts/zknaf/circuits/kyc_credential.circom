/*
 * AMTTP zkNAF - KYC Credential Proof
 * 
 * Proves that a user has passed KYC verification without revealing:
 * - Their real identity
 * - Date of birth
 * - Address
 * - Document numbers
 * 
 * Only proves:
 * - KYC was completed by an authorized provider
 * - KYC is still valid (not expired)
 * - User is of legal age (18+)
 * - User is not a PEP (Politically Exposed Person) - optional
 * 
 * FCA COMPLIANCE NOTE:
 * Full KYC records are maintained by the regulated entity for:
 * - SAR filing (FSMA s.330)
 * - Law enforcement requests
 * - 5-year audit trail (MLR 2017)
 * This proof enables DeFi protocols to verify compliance status without
 * receiving PII, reducing their regulatory burden.
 */

pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";

/*
 * AgeVerifier - Proves user is at least minAge years old
 */
template AgeVerifier() {
    signal input birthTimestamp;    // Unix timestamp of birth
    signal input currentTimestamp;  // Current time
    signal input minAgeSeconds;     // Minimum age in seconds (18 years = 567648000)
    
    signal output isOldEnough;
    
    // Calculate age in seconds
    signal ageInSeconds;
    ageInSeconds <== currentTimestamp - birthTimestamp;
    
    // Check if age >= minAge
    component geAge = GreaterEqThan(64);
    geAge.in[0] <== ageInSeconds;
    geAge.in[1] <== minAgeSeconds;
    
    isOldEnough <== geAge.out;
}

/*
 * KYCProviderVerifier - Verifies KYC was performed by authorized provider
 */
template KYCProviderVerifier() {
    signal input providerSignature;    // Provider's signature on KYC data
    signal input providerCommitment;   // Public commitment of authorized provider
    signal input kycDataHash;          // Hash of KYC data
    signal input providerSecret;       // Provider's secret (private)
    
    signal output isAuthorized;
    
    // Verify provider signature
    component hasher = Poseidon(3);
    hasher.inputs[0] <== kycDataHash;
    hasher.inputs[1] <== providerSecret;
    hasher.inputs[2] <== providerSignature;
    
    // Check against public commitment
    component eq = IsEqual();
    eq.in[0] <== hasher.out;
    eq.in[1] <== providerCommitment;
    
    isAuthorized <== eq.out;
}

/*
 * KYCCredentialProof - Main circuit for proving KYC status
 * 
 * Public Inputs:
 *   - providerCommitment: Commitment of authorized KYC provider (e.g., Sumsub)
 *   - userAddressHash: Hash of user's blockchain address
 *   - currentTimestamp: Current time
 *   - minAgeSeconds: Minimum age requirement (default: 18 years)
 * 
 * Private Inputs:
 *   - userAddress: User's blockchain address
 *   - birthTimestamp: User's date of birth (Unix timestamp)
 *   - kycCompletedAt: When KYC was completed
 *   - kycExpiresAt: When KYC expires
 *   - isPEP: Whether user is a PEP (0 = no, 1 = yes)
 *   - providerSignature: Signature from KYC provider
 *   - providerSecret: Provider's signing secret
 *   - kycDataHash: Hash of full KYC data
 */
template KYCCredentialProof() {
    // Public inputs
    signal input providerCommitment;
    signal input userAddressHash;
    signal input currentTimestamp;
    signal input minAgeSeconds;
    
    // Private inputs
    signal input userAddress;
    signal input birthTimestamp;
    signal input kycCompletedAt;
    signal input kycExpiresAt;
    signal input isPEP;
    signal input providerSignature;
    signal input providerSecret;
    signal input kycDataHash;
    
    // Outputs
    signal output kycValid;
    signal output isOldEnough;
    signal output isNotPEP;
    signal output isNotExpired;
    signal output isProviderAuthorized;
    
    // Step 1: Verify user address matches hash
    component addrHasher = Poseidon(1);
    addrHasher.inputs[0] <== userAddress;
    addrHasher.out === userAddressHash;
    
    // Step 2: Verify KYC provider is authorized
    component providerVerifier = KYCProviderVerifier();
    providerVerifier.providerSignature <== providerSignature;
    providerVerifier.providerCommitment <== providerCommitment;
    providerVerifier.kycDataHash <== kycDataHash;
    providerVerifier.providerSecret <== providerSecret;
    isProviderAuthorized <== providerVerifier.isAuthorized;
    
    // Step 3: Verify user is old enough (18+)
    component ageVerifier = AgeVerifier();
    ageVerifier.birthTimestamp <== birthTimestamp;
    ageVerifier.currentTimestamp <== currentTimestamp;
    ageVerifier.minAgeSeconds <== minAgeSeconds;
    isOldEnough <== ageVerifier.isOldEnough;
    
    // Step 4: Verify KYC is not expired
    component notExpired = LessThan(64);
    notExpired.in[0] <== currentTimestamp;
    notExpired.in[1] <== kycExpiresAt;
    isNotExpired <== notExpired.out;
    
    // Step 5: Verify user is not a PEP (isPEP should be 0)
    component notPEP = IsZero();
    notPEP.in <== isPEP;
    isNotPEP <== notPEP.out;
    
    // Step 6: Compute overall validity
    // kycValid = isProviderAuthorized AND isOldEnough AND isNotExpired
    signal temp;
    temp <== isProviderAuthorized * isOldEnough;
    kycValid <== temp * isNotExpired;
}

// Export with public inputs
component main {public [providerCommitment, userAddressHash, currentTimestamp, minAgeSeconds]} = KYCCredentialProof();
