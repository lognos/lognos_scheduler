"""
FastAPI dependencies for authentication and authorization.
"""
from typing import Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logfire

from sch_backend.utils.supabase_client import get_supabase

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Validate JWT token and return current user info.
    
    Extracts the bearer token from Authorization header and validates it
    against Supabase Auth.
    
    Returns:
        Dict containing user information including 'email' and 'id'
    
    Raises:
        HTTPException 401: If token is invalid or expired
    """
    token = credentials.credentials
    
    try:
        supabase = get_supabase()
        # Validate token with Supabase Auth
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = user_response.user
        return {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logfire.error("Token validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
