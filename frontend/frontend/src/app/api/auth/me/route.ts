/**
 * Session/Me API Route
 * 
 * Returns current user session information
 */

import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('Authorization');
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json(
        { success: false, error: 'No valid session' },
        { status: 401 }
      );
    }
    
    const token = authHeader.substring(7);
    
    // In production, validate the token and look up the user
    // For now, we'll decode mock session info from localStorage
    // This is just a placeholder - real implementation would use JWT
    
    if (!token || token === 'undefined') {
      return NextResponse.json(
        { success: false, error: 'Invalid session token' },
        { status: 401 }
      );
    }
    
    // Return mock user data (in production, look up from database)
    return NextResponse.json({
      success: true,
      user: {
        id: 'current_user',
        email: 'user@amttp.io',
        displayName: 'Current User',
        walletAddress: null,
        createdAt: new Date().toISOString(),
      },
      session: {
        token,
        expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      },
    });
  } catch (error) {
    console.error('Session check error:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to validate session' },
      { status: 500 }
    );
  }
}
