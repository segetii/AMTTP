/**
 * Logout API Route
 * 
 * Handles user logout and session invalidation
 */

import { NextRequest, NextResponse } from 'next/server';

// In production, this would invalidate the session in the database
const invalidatedSessions: Set<string> = new Set();

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('Authorization');
    
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const token = authHeader.substring(7);
      invalidatedSessions.add(token);
    }
    
    return NextResponse.json({
      success: true,
      message: 'Logged out successfully',
    });
  } catch (error) {
    console.error('Logout error:', error);
    return NextResponse.json(
      { success: false, error: 'Logout failed' },
      { status: 500 }
    );
  }
}
