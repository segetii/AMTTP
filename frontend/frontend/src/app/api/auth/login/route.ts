/**
 * Login API Route
 * 
 * Handles user authentication with email/password or wallet signature
 */

import { NextRequest, NextResponse } from 'next/server';

// Mock database (in production, use a real database)
// This should be shared with register route in a real implementation
const users: Map<string, {
  id: string;
  email?: string;
  passwordHash?: string;
  walletAddress?: string;
  displayName?: string;
  createdAt: string;
}> = new Map();

// Add a demo user for testing
users.set('demo_user', {
  id: 'demo_user',
  email: 'demo@amttp.io',
  passwordHash: 'hashed_Demo123!',
  walletAddress: '0x742d35Cc6634C0532925a3b844Bc9e7595f1234',
  displayName: 'Demo User',
  createdAt: '2024-01-01T00:00:00Z',
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password, walletAddress, signature, signedMessage, authMethod } = body;
    
    let user;
    
    if (authMethod === 'email') {
      // Email/password authentication
      if (!email || !password) {
        return NextResponse.json(
          { success: false, error: 'Email and password are required' },
          { status: 400 }
        );
      }
      
      // Find user by email
      user = Array.from(users.values()).find(u => u.email === email);
      
      if (!user) {
        return NextResponse.json(
          { success: false, error: 'Invalid email or password' },
          { status: 401 }
        );
      }
      
      // Verify password (in production, use bcrypt.compare)
      if (user.passwordHash !== `hashed_${password}`) {
        return NextResponse.json(
          { success: false, error: 'Invalid email or password' },
          { status: 401 }
        );
      }
    } else if (authMethod === 'wallet') {
      // Wallet-based authentication
      if (!walletAddress) {
        return NextResponse.json(
          { success: false, error: 'Wallet address is required' },
          { status: 400 }
        );
      }
      
      // Find user by wallet address
      user = Array.from(users.values()).find(
        u => u.walletAddress?.toLowerCase() === walletAddress.toLowerCase()
      );
      
      // If signature verification is required
      if (signature && signedMessage) {
        // In production, verify the signature here using ethers.js or similar
        // const recoveredAddress = ethers.utils.verifyMessage(signedMessage, signature);
        // if (recoveredAddress.toLowerCase() !== walletAddress.toLowerCase()) {
        //   return NextResponse.json({ success: false, error: 'Invalid signature' }, { status: 401 });
        // }
      }
      
      // Auto-create user for wallet login if not exists
      if (!user) {
        const userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        user = {
          id: userId,
          walletAddress,
          displayName: `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`,
          createdAt: new Date().toISOString(),
        };
        users.set(userId, user);
      }
    } else {
      return NextResponse.json(
        { success: false, error: 'Invalid authentication method' },
        { status: 400 }
      );
    }
    
    // Generate session token
    const sessionToken = `session_${Date.now()}_${Math.random().toString(36).substr(2, 16)}`;
    
    // Generate refresh token
    const refreshToken = `refresh_${Date.now()}_${Math.random().toString(36).substr(2, 16)}`;
    
    // Return success response
    return NextResponse.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        walletAddress: user.walletAddress,
        displayName: user.displayName,
        createdAt: user.createdAt,
      },
      sessionToken,
      refreshToken,
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 24 hours
    });
  } catch (error) {
    console.error('Login error:', error);
    return NextResponse.json(
      { success: false, error: 'Login failed. Please try again.' },
      { status: 500 }
    );
  }
}
