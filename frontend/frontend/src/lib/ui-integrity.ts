/**
 * AMTTP UI Integrity Protection
 * 
 * Prevents Bybit-style attacks where attackers manipulate the UI/signing logic
 * to trick users into approving malicious transactions.
 * 
 * Protection layers:
 * 1. Component hash verification - detect DOM/logic tampering
 * 2. Transaction intent signing - sign actual intent, not displayed data
 * 3. Server-side hash validation - verify UI hasn't been modified
 * 4. Visual confirmation layer - show hash-verified data in isolated context
 */

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const INTEGRITY_VERSION = "1.0.0";

// Known good hashes (should be loaded from server in production)
// These are updated when legitimate deployments happen
const TRUSTED_COMPONENT_HASHES: Record<string, string> = {};

// ═══════════════════════════════════════════════════════════════════════════════
// CRYPTO UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Generate SHA-256 hash of content
 */
async function sha256(content: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(content);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Generate hash of an object (deterministic JSON serialization)
 */
async function hashObject(obj: unknown): Promise<string> {
  const sorted = JSON.stringify(obj, Object.keys(obj as object).sort());
  return sha256(sorted);
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRANSACTION INTENT
// ═══════════════════════════════════════════════════════════════════════════════

export interface TransactionIntent {
  // Core transaction data
  type: "TRANSFER" | "BATCH_TRANSFER" | "CONTRACT_CALL" | "APPROVAL";
  fromAddress: string;
  toAddress: string;
  valueWei: string;
  valueEth: string;
  
  // Chain info
  chainId: number;
  networkName: string;
  
  // Token info (for token transfers)
  tokenAddress?: string;
  tokenSymbol?: string;
  tokenDecimals?: number;
  
  // Contract call data
  contractMethod?: string;
  contractArgs?: unknown[];
  
  // Metadata
  timestamp: number;
  nonce: number;
  userAgent: string;
  
  // UI integrity
  uiComponentHash: string;
  displayedDataHash: string;
}

export interface SignedIntent {
  intent: TransactionIntent;
  intentHash: string;
  signature: string;
  signerAddress: string;
  signedAt: number;
}

/**
 * Create a transaction intent object with all verified data
 */
export async function createTransactionIntent(
  params: {
    type: TransactionIntent["type"];
    fromAddress: string;
    toAddress: string;
    valueWei: string;
    chainId: number;
    networkName: string;
    tokenAddress?: string;
    tokenSymbol?: string;
    tokenDecimals?: number;
    contractMethod?: string;
    contractArgs?: unknown[];
  },
  uiComponentHash: string,
  displayedData: Record<string, unknown>
): Promise<TransactionIntent> {
  const valueEth = (BigInt(params.valueWei) / BigInt(10 ** 18)).toString();
  
  return {
    type: params.type,
    fromAddress: params.fromAddress.toLowerCase(),
    toAddress: params.toAddress.toLowerCase(),
    valueWei: params.valueWei,
    valueEth,
    chainId: params.chainId,
    networkName: params.networkName,
    tokenAddress: params.tokenAddress?.toLowerCase(),
    tokenSymbol: params.tokenSymbol,
    tokenDecimals: params.tokenDecimals,
    contractMethod: params.contractMethod,
    contractArgs: params.contractArgs,
    timestamp: Date.now(),
    nonce: Math.floor(Math.random() * 1000000),
    userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
    uiComponentHash,
    displayedDataHash: await hashObject(displayedData),
  };
}

/**
 * Generate the intent hash that user will sign
 */
export async function getIntentHash(intent: TransactionIntent): Promise<string> {
  // Create a canonical representation
  const canonical = {
    v: INTEGRITY_VERSION,
    type: intent.type,
    from: intent.fromAddress,
    to: intent.toAddress,
    value: intent.valueWei,
    chain: intent.chainId,
    token: intent.tokenAddress || null,
    method: intent.contractMethod || null,
    ts: intent.timestamp,
    nonce: intent.nonce,
    uiHash: intent.uiComponentHash,
    dataHash: intent.displayedDataHash,
  };
  
  return hashObject(canonical);
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI COMPONENT INTEGRITY
// ═══════════════════════════════════════════════════════════════════════════════

export interface ComponentIntegrity {
  componentId: string;
  sourceHash: string;
  domHash: string;
  eventHandlersHash: string;
  combinedHash: string;
  verified: boolean;
  timestamp: number;
}

/**
 * Capture the integrity state of a UI component
 */
export async function captureComponentIntegrity(
  componentId: string,
  componentElement: HTMLElement | null,
  sourceCode?: string
): Promise<ComponentIntegrity> {
  const timestamp = Date.now();
  
  // Hash the source code (if available)
  const sourceHash = sourceCode ? await sha256(sourceCode) : "not-available";
  
  // Hash the current DOM structure
  let domHash = "not-available";
  if (componentElement) {
    // Remove dynamic content, keep structure
    const structure = extractDOMStructure(componentElement);
    domHash = await sha256(structure);
  }
  
  // Hash event handlers attached to the component
  let eventHandlersHash = "not-available";
  if (componentElement) {
    const handlers = extractEventHandlers(componentElement);
    eventHandlersHash = await sha256(JSON.stringify(handlers));
  }
  
  // Combined hash
  const combinedHash = await sha256(`${sourceHash}:${domHash}:${eventHandlersHash}`);
  
  // Verify against known good hash
  const trustedHash = TRUSTED_COMPONENT_HASHES[componentId];
  const verified = trustedHash ? trustedHash === combinedHash : false;
  
  return {
    componentId,
    sourceHash,
    domHash,
    eventHandlersHash,
    combinedHash,
    verified,
    timestamp,
  };
}

/**
 * Extract DOM structure without dynamic content
 */
function extractDOMStructure(element: HTMLElement): string {
  const clone = element.cloneNode(true) as HTMLElement;
  
  // Remove dynamic content
  const dynamicSelectors = [
    "[data-dynamic]",
    "[data-value]",
    "input",
    "textarea",
    ".timestamp",
    ".balance",
    ".price",
  ];
  
  dynamicSelectors.forEach((selector) => {
    clone.querySelectorAll(selector).forEach((el) => {
      if (el instanceof HTMLElement) {
        el.textContent = "[DYNAMIC]";
        // Keep attributes but clear dynamic values
        Array.from(el.attributes).forEach((attr) => {
          if (attr.name.startsWith("data-") && attr.name !== "data-testid") {
            el.setAttribute(attr.name, "[DYNAMIC]");
          }
        });
      }
    });
  });
  
  // Return structural representation
  return clone.innerHTML
    .replace(/\s+/g, " ")
    .replace(/<!--.*?-->/g, "")
    .trim();
}

/**
 * Extract event handler information from element
 */
function extractEventHandlers(element: HTMLElement): string[] {
  const handlers: string[] = [];
  
  // Check inline handlers
  const handlerAttrs = [
    "onclick",
    "onsubmit",
    "onchange",
    "oninput",
    "onkeydown",
    "onkeyup",
  ];
  
  const checkElement = (el: Element) => {
    handlerAttrs.forEach((attr) => {
      const handler = el.getAttribute(attr);
      if (handler) {
        handlers.push(`${attr}:${handler.substring(0, 100)}`);
      }
    });
  };
  
  checkElement(element);
  element.querySelectorAll("*").forEach(checkElement);
  
  return handlers.sort();
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAYMENT PAGE INTEGRITY
// ═══════════════════════════════════════════════════════════════════════════════

export interface PaymentPageIntegrity {
  pageHash: string;
  scriptsHash: string;
  stylesHash: string;
  formsHash: string;
  buttonsHash: string;
  combinedHash: string;
  timestamp: number;
  warnings: string[];
}

/**
 * Capture complete payment page integrity
 */
export async function capturePaymentPageIntegrity(): Promise<PaymentPageIntegrity> {
  const warnings: string[] = [];
  
  // Hash all scripts on the page
  const scripts = Array.from(document.querySelectorAll("script"));
  const scriptContents = scripts.map((s) => s.src || s.textContent || "").join("|");
  const scriptsHash = await sha256(scriptContents);
  
  // Check for suspicious inline scripts
  scripts.forEach((script, i) => {
    if (script.textContent && script.textContent.includes("eval(")) {
      warnings.push(`Script ${i} contains eval()`);
    }
    if (script.textContent && script.textContent.includes("document.write")) {
      warnings.push(`Script ${i} contains document.write`);
    }
  });
  
  // Hash stylesheets
  const styles = Array.from(document.querySelectorAll("style, link[rel='stylesheet']"));
  const styleContents = styles.map((s) => {
    if (s instanceof HTMLStyleElement) return s.textContent || "";
    if (s instanceof HTMLLinkElement) return s.href;
    return "";
  }).join("|");
  const stylesHash = await sha256(styleContents);
  
  // Hash form structures
  const forms = Array.from(document.querySelectorAll("form"));
  const formStructures = forms.map((f) => {
    return {
      action: f.action,
      method: f.method,
      inputs: Array.from(f.querySelectorAll("input, select, textarea")).map((i) => ({
        name: (i as HTMLInputElement).name,
        type: (i as HTMLInputElement).type,
      })),
    };
  });
  const formsHash = await sha256(JSON.stringify(formStructures));
  
  // Hash critical buttons
  const buttons = Array.from(document.querySelectorAll(
    "button[type='submit'], .btn-primary, [data-action='transfer'], [data-action='approve']"
  ));
  const buttonData = buttons.map((b) => ({
    text: b.textContent?.trim(),
    className: b.className,
    disabled: (b as HTMLButtonElement).disabled,
  }));
  const buttonsHash = await sha256(JSON.stringify(buttonData));
  
  // Hash the entire page structure
  const pageStructure = document.documentElement.outerHTML
    .replace(/<script[\s\S]*?<\/script>/gi, "[SCRIPT]")
    .replace(/<style[\s\S]*?<\/style>/gi, "[STYLE]")
    .replace(/\s+/g, " ");
  const pageHash = await sha256(pageStructure);
  
  // Combined integrity hash
  const combinedHash = await sha256(
    `${pageHash}:${scriptsHash}:${stylesHash}:${formsHash}:${buttonsHash}`
  );
  
  return {
    pageHash,
    scriptsHash,
    stylesHash,
    formsHash,
    buttonsHash,
    combinedHash,
    timestamp: Date.now(),
    warnings,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MUTATION DETECTION
// ═══════════════════════════════════════════════════════════════════════════════

export interface MutationAlert {
  type: "script_injection" | "dom_modification" | "handler_change" | "style_change";
  severity: "critical" | "high" | "medium" | "low";
  element: string;
  details: string;
  timestamp: number;
}

type MutationAlertCallback = (alert: MutationAlert) => void;

let mutationObserver: MutationObserver | null = null;
let alertCallbacks: MutationAlertCallback[] = [];

/**
 * Start monitoring for suspicious mutations
 */
export function startMutationMonitoring(
  targetElement: HTMLElement,
  onAlert: MutationAlertCallback
): void {
  alertCallbacks.push(onAlert);
  
  if (mutationObserver) {
    return; // Already monitoring
  }
  
  mutationObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      checkMutation(mutation);
    });
  });
  
  mutationObserver.observe(targetElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeOldValue: true,
    characterData: true,
  });
}

/**
 * Stop mutation monitoring
 */
export function stopMutationMonitoring(): void {
  if (mutationObserver) {
    mutationObserver.disconnect();
    mutationObserver = null;
  }
  alertCallbacks = [];
}

/**
 * Check a mutation for suspicious activity
 */
function checkMutation(mutation: MutationRecord): void {
  const alerts: MutationAlert[] = [];
  
  // Check for script injection
  if (mutation.type === "childList") {
    mutation.addedNodes.forEach((node) => {
      if (node instanceof HTMLScriptElement) {
        alerts.push({
          type: "script_injection",
          severity: "critical",
          element: node.src || "inline",
          details: `Script injected: ${node.src || node.textContent?.substring(0, 100)}`,
          timestamp: Date.now(),
        });
      }
      
      // Check for iframes (potential clickjacking)
      if (node instanceof HTMLIFrameElement) {
        alerts.push({
          type: "dom_modification",
          severity: "critical",
          element: node.src || "inline",
          details: `IFrame injected: ${node.src}`,
          timestamp: Date.now(),
        });
      }
    });
  }
  
  // Check for handler modifications
  if (mutation.type === "attributes") {
    const handlerAttrs = ["onclick", "onsubmit", "onchange", "oninput"];
    if (handlerAttrs.includes(mutation.attributeName || "")) {
      alerts.push({
        type: "handler_change",
        severity: "high",
        element: (mutation.target as HTMLElement).tagName,
        details: `Event handler modified: ${mutation.attributeName}`,
        timestamp: Date.now(),
      });
    }
    
    // Check for action/href modifications on forms/links
    if (mutation.attributeName === "action" || mutation.attributeName === "href") {
      const newValue = (mutation.target as HTMLElement).getAttribute(mutation.attributeName);
      if (newValue && !newValue.startsWith(window.location.origin)) {
        alerts.push({
          type: "dom_modification",
          severity: "critical",
          element: (mutation.target as HTMLElement).tagName,
          details: `External redirect detected: ${newValue}`,
          timestamp: Date.now(),
        });
      }
    }
  }
  
  // Notify all callbacks
  alerts.forEach((alert) => {
    alertCallbacks.forEach((cb) => cb(alert));
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// VISUAL CONFIRMATION LAYER
// ═══════════════════════════════════════════════════════════════════════════════

export interface ConfirmationData {
  intentHash: string;
  toAddress: string;
  toAddressChecksum: string;
  valueEth: string;
  valueUsd: string;
  networkName: string;
  warningLevel: "none" | "caution" | "warning" | "danger";
  warnings: string[];
}

/**
 * Generate secure confirmation data for display in isolated layer
 */
export async function generateConfirmationData(
  intent: TransactionIntent,
  riskScore: number,
  warnings: string[]
): Promise<ConfirmationData> {
  const intentHash = await getIntentHash(intent);
  
  // Determine warning level based on risk
  let warningLevel: ConfirmationData["warningLevel"] = "none";
  if (riskScore > 80) warningLevel = "danger";
  else if (riskScore > 60) warningLevel = "warning";
  else if (riskScore > 40) warningLevel = "caution";
  
  // Generate checksum address (EIP-55)
  const toAddressChecksum = toChecksumAddress(intent.toAddress);
  
  return {
    intentHash: intentHash.substring(0, 16) + "...", // Truncated for display
    toAddress: intent.toAddress,
    toAddressChecksum,
    valueEth: intent.valueEth,
    valueUsd: "N/A", // Would be fetched from price oracle
    networkName: intent.networkName,
    warningLevel,
    warnings,
  };
}

/**
 * Convert address to checksum format (EIP-55)
 */
function toChecksumAddress(address: string): string {
  // Simplified - in production use ethers.getAddress()
  const addr = address.toLowerCase().replace("0x", "");
  // For now return as-is, proper implementation needs keccak256
  return "0x" + addr;
}

// ═══════════════════════════════════════════════════════════════════════════════
// INTEGRITY VERIFICATION API
// ═══════════════════════════════════════════════════════════════════════════════

export interface IntegrityReport {
  version: string;
  pageIntegrity: PaymentPageIntegrity;
  componentIntegrity: ComponentIntegrity[];
  mutationAlerts: MutationAlert[];
  isCompromised: boolean;
  riskLevel: "safe" | "suspicious" | "compromised";
  timestamp: number;
}

/**
 * Generate a full integrity report for the current page
 */
export async function generateIntegrityReport(
  components: Array<{ id: string; element: HTMLElement | null; source?: string }>
): Promise<IntegrityReport> {
  const pageIntegrity = await capturePaymentPageIntegrity();
  
  const componentIntegrity = await Promise.all(
    components.map((c) => captureComponentIntegrity(c.id, c.element, c.source))
  );
  
  // Determine if compromised
  const hasWarnings = pageIntegrity.warnings.length > 0;
  const hasUnverifiedComponents = componentIntegrity.some((c) => !c.verified);
  
  let riskLevel: IntegrityReport["riskLevel"] = "safe";
  let isCompromised = false;
  
  if (pageIntegrity.warnings.some((w) => w.includes("eval"))) {
    riskLevel = "compromised";
    isCompromised = true;
  } else if (hasWarnings || hasUnverifiedComponents) {
    riskLevel = "suspicious";
  }
  
  return {
    version: INTEGRITY_VERSION,
    pageIntegrity,
    componentIntegrity,
    mutationAlerts: [], // Would be populated from monitoring
    isCompromised,
    riskLevel,
    timestamp: Date.now(),
  };
}

/**
 * Verify integrity report with server
 */
export async function verifyWithServer(
  report: IntegrityReport,
  apiEndpoint: string
): Promise<{ valid: boolean; serverHash: string; message: string }> {
  try {
    const response = await fetch(`${apiEndpoint}/verify-integrity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
    });
    
    if (!response.ok) {
      return {
        valid: false,
        serverHash: "",
        message: `Server error: ${response.status}`,
      };
    }
    
    return await response.json();
  } catch (error) {
    return {
      valid: false,
      serverHash: "",
      message: `Verification failed: ${error}`,
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORTS
// ═══════════════════════════════════════════════════════════════════════════════

export {
  sha256,
  hashObject,
  INTEGRITY_VERSION,
};
