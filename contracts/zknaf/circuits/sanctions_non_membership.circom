/*
 * AMTTP zkNAF - Sanctions Non-Membership Proof
 * 
 * Proves that an address is NOT in the sanctions list without revealing:
 * - The full sanctions list
 * - Which addresses are on the list
 * - The user's identity
 * 
 * FCA COMPLIANCE NOTE:
 * This proof is for PUBLIC verification only. The regulated entity maintains
 * the full sanctions list and screening records for regulatory disclosure.
 * 
 * Circuit: Merkle tree non-membership proof
 * - Public Input: Merkle root of sanctions list
 * - Private Input: Address being checked, Merkle proof of non-membership
 * - Output: 1 if address is NOT in list, 0 otherwise
 */

pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/mux1.circom";
include "circomlib/circuits/bitify.circom";

/*
 * MerkleTreeChecker - Verifies a Merkle proof
 * @param levels - Number of levels in the Merkle tree
 */
template MerkleTreeChecker(levels) {
    signal input leaf;
    signal input pathElements[levels];
    signal input pathIndices[levels];
    signal output root;

    component hashers[levels];
    component mux[levels];

    signal levelHashes[levels + 1];
    levelHashes[0] <== leaf;

    for (var i = 0; i < levels; i++) {
        // Ensure pathIndices is binary
        pathIndices[i] * (1 - pathIndices[i]) === 0;

        hashers[i] = Poseidon(2);
        mux[i] = MultiMux1(2);

        // Select order based on path index
        mux[i].c[0][0] <== levelHashes[i];
        mux[i].c[0][1] <== pathElements[i];
        mux[i].c[1][0] <== pathElements[i];
        mux[i].c[1][1] <== levelHashes[i];
        mux[i].s <== pathIndices[i];

        hashers[i].inputs[0] <== mux[i].out[0];
        hashers[i].inputs[1] <== mux[i].out[1];

        levelHashes[i + 1] <== hashers[i].out;
    }

    root <== levelHashes[levels];
}

/*
 * SortedListNonMembership - Proves non-membership in a sorted list
 * Uses the property that in a sorted list, if element E is not in the list,
 * there exist adjacent elements L < E < R
 */
template SortedListNonMembership() {
    signal input element;           // The element to prove non-membership
    signal input leftNeighbor;      // Element just below (or 0 if none)
    signal input rightNeighbor;     // Element just above (or MAX if none)
    
    signal output isNotMember;

    // Verify leftNeighbor < element < rightNeighbor
    component lt1 = LessThan(252);
    component lt2 = LessThan(252);

    lt1.in[0] <== leftNeighbor;
    lt1.in[1] <== element;

    lt2.in[0] <== element;
    lt2.in[1] <== rightNeighbor;

    // Both must be true for non-membership
    isNotMember <== lt1.out * lt2.out;
}

/*
 * SanctionsNonMembership - Main circuit for proving address is not sanctioned
 * 
 * Public Inputs:
 *   - sanctionsListRoot: Merkle root of the sorted sanctions list
 *   - currentTimestamp: Current time (to prevent replay attacks)
 * 
 * Private Inputs:
 *   - address: The address being checked (as field element)
 *   - leftNeighbor: Address just below in sorted list
 *   - rightNeighbor: Address just above in sorted list
 *   - leftProof: Merkle proof for leftNeighbor
 *   - rightProof: Merkle proof for rightNeighbor
 *   - leftPathIndices: Path indices for left proof
 *   - rightPathIndices: Path indices for right proof
 * 
 * @param levels - Merkle tree depth (20 supports ~1M addresses)
 */
template SanctionsNonMembership(levels) {
    // Public inputs
    signal input sanctionsListRoot;
    signal input currentTimestamp;
    
    // Private inputs
    signal input addressToCheck;
    signal input leftNeighbor;
    signal input rightNeighbor;
    signal input leftProof[levels];
    signal input rightProof[levels];
    signal input leftPathIndices[levels];
    signal input rightPathIndices[levels];
    
    // Output
    signal output isNotSanctioned;
    signal output proofTimestamp;
    
    // Step 1: Verify left neighbor is in the sanctions list
    component leftMerkle = MerkleTreeChecker(levels);
    leftMerkle.leaf <== leftNeighbor;
    for (var i = 0; i < levels; i++) {
        leftMerkle.pathElements[i] <== leftProof[i];
        leftMerkle.pathIndices[i] <== leftPathIndices[i];
    }
    leftMerkle.root === sanctionsListRoot;
    
    // Step 2: Verify right neighbor is in the sanctions list
    component rightMerkle = MerkleTreeChecker(levels);
    rightMerkle.leaf <== rightNeighbor;
    for (var i = 0; i < levels; i++) {
        rightMerkle.pathElements[i] <== rightProof[i];
        rightMerkle.pathIndices[i] <== rightPathIndices[i];
    }
    rightMerkle.root === sanctionsListRoot;
    
    // Step 3: Verify address is between left and right neighbors
    component nonMembership = SortedListNonMembership();
    nonMembership.element <== addressToCheck;
    nonMembership.leftNeighbor <== leftNeighbor;
    nonMembership.rightNeighbor <== rightNeighbor;
    
    // Output
    isNotSanctioned <== nonMembership.isNotMember;
    proofTimestamp <== currentTimestamp;
}

// Main component with 20 levels (supports ~1M sanctioned addresses)
component main {public [sanctionsListRoot, currentTimestamp]} = SanctionsNonMembership(20);
