/**
 * Registration API Route
 * 
 * Handles user registration with email/password or wallet
 */

import { NextRequest, NextResponse } from 'next/server';

// Mock database (in production, use a real database)
const users: Map<string, {
  id: string;
  email?: string;
  passwordHash?: string;
  walletAddress?: string;
  displayName?: string;
  createdAt: string;
}> = new Map();

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password, walletAddress, displayName, authMethod } = body;
    
    // Validate input
    if (authMethod === 'email') {
      if (!email || !password) {
        return NextResponse.json(
          { success: false, error: 'Email and password are required' },
          { status: 400 }
        );
      }
      
      // Check if email already exists
      const existingUser = Array.from(users.values()).find(u => u.email === email);
      if (existingUser) {
        return NextResponse.json(
          { success: false, error: 'An account with this email already exists' },
          { status: 409 }
        );
      }
      
      // Validate password strength
      if (password.length < 8) {
        return NextResponse.json(
          { success: false, error: 'Password must be at least 8 characters' },
          { status: 400 }
        );
      }
    } else if (authMethod === 'wallet') {
      if (!walletAddress) {
        return NextResponse.json(
          { success: false, error: 'Wallet address is required' },
          { status: 400 }
        );
      }
      
      // Check if wallet already exists
      const existingUser = Array.from(users.values()).find(u => u.walletAddress === walletAddress);
      if (existingUser) {
        return NextResponse.json(
          { success: false, error: 'An account with this wallet already exists' },
          { status: 409 }
        );
      }
    } else {
      return NextResponse.json(
        { success: false, error: 'Invalid authentication method' },
        { status: 400 }
      );
    }
    
    // Generate user ID
    const userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Create user (in production, hash the password properly)
    const user = {
      id: userId,
      email: email || undefined,
      passwordHash: password ? `hashed_${password}` : undefined, // In production, use bcrypt
      walletAddress: walletAddress || undefined,
      displayName: displayName || email?.split('@')[0] || `User_${userId.slice(-6)}`,
      createdAt: new Date().toISOString(),
    };
    
    users.set(userId, user);
    
    // Generate session token (in production, use JWT or similar)
    const sessionToken = `session_${Date.now()}_${Math.random().toString(36).substr(2, 16)}`;
    
    // Return success response (without password)
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
    });
  } catch (error) {
    console.error('Registration error:', error);
    return NextResponse.json(
      { success: false, error: 'Registration failed. Please try again.' },
      { status: 500 }
    );
  }
}
