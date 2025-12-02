'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'
import { Session } from '@supabase/supabase-js'
import { supabase } from '../../utils/supabase'
import { AuthUser, User } from '../../types/auth'
import { useRouter, usePathname } from 'next/navigation'

interface AuthContextType {
    user: AuthUser | null
    session: Session | null
    loading: boolean
    signInWithMicrosoft: () => Promise<void>
    signOut: () => Promise<void>
    isAuthorized: boolean
}

const AuthContext = createContext<AuthContextType>({
    user: null,
    session: null,
    loading: true,
    signInWithMicrosoft: async () => { },
    signOut: async () => { },
    isAuthorized: false,
})

export const useAuth = () => {
    const context = useContext(AuthContext)
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}

// Cache keys
const AUTH_CACHE_KEY = 'lognos_auth_cache'

interface AuthCache {
    user: AuthUser | null
    isAuthorized: boolean
    timestamp: number
    sessionId: string
}

const getAuthCache = (): AuthCache | null => {
    if (typeof window === 'undefined') return null
    try {
        const cached = localStorage.getItem(AUTH_CACHE_KEY)
        if (!cached) return null
        const parsed = JSON.parse(cached)
        // Cache valid for 1 hour
        if (Date.now() - parsed.timestamp > 3600000) {
            localStorage.removeItem(AUTH_CACHE_KEY)
            return null
        }
        return parsed
    } catch (e) {
        return null
    }
}

const setAuthCache = (user: AuthUser | null, isAuthorized: boolean, sessionId: string) => {
    if (typeof window === 'undefined') return
    const cache: AuthCache = {
        user,
        isAuthorized,
        timestamp: Date.now(),
        sessionId
    }
    localStorage.setItem(AUTH_CACHE_KEY, JSON.stringify(cache))
}

const clearAuthCache = () => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(AUTH_CACHE_KEY)
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<AuthUser | null>(null)
    const [session, setSession] = useState<Session | null>(null)
    const [loading, setLoading] = useState(true)
    const [isAuthorized, setIsAuthorized] = useState(false)
    const [isInitialized, setIsInitialized] = useState(false)
    const router = useRouter()
    const pathname = usePathname()

    // Check if user is in the authorized users table
    const checkUserAuthorization = async (email: string): Promise<User | null> => {
        try {
            const { data, error } = await supabase
                .from('users')
                .select('*')
                .eq('user_email', email)
                .single()

            if (error) {
                console.error('Error checking user authorization:', error)
                return null
            }

            return data
        } catch (error) {
            console.error('Error checking user authorization:', error)
            return null
        }
    }

    // Smart session change handler that respects cache
    const handleSessionChange = async (session: Session | null, forceRefresh = false) => {

        // Don't process session changes during initial setup unless forced
        if (!forceRefresh && !isInitialized) {
            return
        }

        setLoading(true)

        if (session?.user) {
            const email = session.user.email
            if (email) {
                // Check cache first unless forced refresh
                if (!forceRefresh) {
                    const cachedAuth = getAuthCache()
                    const currentSessionId = session.access_token

                    if (cachedAuth && cachedAuth.sessionId === currentSessionId) {
                        setUser(cachedAuth.user)
                        setIsAuthorized(cachedAuth.isAuthorized)
                        setLoading(false)
                        return
                    }
                }

                // Check if user is authorized
                const authorizedUser = await checkUserAuthorization(email)

                if (authorizedUser) {
                    const authUser: AuthUser = {
                        id: session.user.id,
                        email: session.user.email || '',
                        name: session.user.user_metadata?.name || authorizedUser.user_name,
                        user_email: authorizedUser.user_email,
                        user_name: authorizedUser.user_name,
                        user_role: authorizedUser.user_role,
                        user_cellphone: authorizedUser.user_cellphone,
                        preferred_language: authorizedUser.preferred_language,
                        first_name: authorizedUser.first_name,
                    }

                    setUser(authUser)
                    setIsAuthorized(true)

                    // Update cache with new auth state
                    setAuthCache(authUser, true, session.access_token)
                } else {
                    // User not authorized - sign them out
                    console.warn(`User ${email} is not authorized to access this application`)
                    await supabase.auth.signOut()
                    setUser(null)
                    setIsAuthorized(false)
                    clearAuthCache()
                    alert('You are not authorized to access this application. Please contact your administrator.')
                }
            }
        } else {
            setUser(null)
            setIsAuthorized(false)
            clearAuthCache()
        }

        setLoading(false)
    }

    // Initialize auth state from cache or fresh
    const initializeAuth = async () => {

        // Try to get current session
        const { data: { session } } = await supabase.auth.getSession()
        setSession(session)

        if (!session) {
            setUser(null)
            setIsAuthorized(false)
            setLoading(false)
            clearAuthCache()
            setIsInitialized(true)
            return
        }

        // Check if we have valid cached auth data
        const cachedAuth = getAuthCache()
        const currentSessionId = session.access_token

        if (cachedAuth && cachedAuth.sessionId === currentSessionId) {
            setUser(cachedAuth.user)
            setIsAuthorized(cachedAuth.isAuthorized)
            setLoading(false)
            setIsInitialized(true)
            return
        }

        // Cache miss or expired - perform full auth check
        await handleSessionChange(session, true) // Force refresh for initial load
        setIsInitialized(true)
    }

    useEffect(() => {
        // Page Visibility API - prevent re-initialization on tab focus
        let initializationPromise: Promise<void> | null = null

        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible' && isInitialized) {
                // Don't re-initialize if already initialized - rely on cache
                return
            }
        }

        const initializeOnce = async () => {
            if (!initializationPromise) {
                initializationPromise = initializeAuth()
            }
            return initializationPromise
        }

        // Initialize auth state only once
        initializeOnce()

        // Listen for page visibility changes
        document.addEventListener('visibilitychange', handleVisibilityChange)

        // Listen for auth changes (but with cache respect)
        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            setSession(session)

            // Only call handleSessionChange for actual auth events, not initial load
            if (isInitialized && _event !== 'INITIAL_SESSION') {
                handleSessionChange(session, false) // Don't force refresh for auth changes
            }
        })

        return () => {
            document.removeEventListener('visibilitychange', handleVisibilityChange)
            subscription.unsubscribe()
        }
    }, []) // Keep empty dependency array but use isInitialized flag

    // Route protection effect
    useEffect(() => {
        if (!loading && !isAuthorized && pathname !== '/login') {
            router.push('/login')
        }
        if (!loading && isAuthorized && pathname === '/login') {
            router.push('/')
        }
    }, [loading, isAuthorized, pathname, router])

    const signInWithMicrosoft = async () => {
        try {
            const { error } = await supabase.auth.signInWithOAuth({
                provider: 'azure',
                options: {
                    redirectTo: `${window.location.origin}/`,
                    scopes: 'openid profile email'
                }
            })

            if (error) {
                console.error('Error signing in with Microsoft:', error)
                throw error
            }
        } catch (error) {
            console.error('Microsoft sign in error:', error)
            throw error
        }
    }

    const signOut = async () => {
        try {
            // Clear auth cache first
            clearAuthCache()

            // Clear local state immediately
            setUser(null)
            setIsAuthorized(false)
            setSession(null)

            // Sign out from Supabase with proper scope
            const { error } = await supabase.auth.signOut({ scope: 'global' })
            if (error) {
                console.error('Error signing out:', error)
                throw error
            }

            // Clear any local storage that might be persisting auth state
            localStorage.removeItem('supabase.auth.token')

            router.push('/login')
        } catch (error) {
            console.error('Sign out error:', error)
            // Even if there's an error, clear local state
            clearAuthCache()
            setUser(null)
            setIsAuthorized(false)
            setSession(null)
            router.push('/login')
            throw error
        }
    }

    const value: AuthContextType = {
        user,
        session,
        loading,
        signInWithMicrosoft,
        signOut,
        isAuthorized,
    }

    return (
        <AuthContext.Provider value={value}>
            {!loading || pathname === '/login' ? children : (
                <div className="min-h-screen flex items-center justify-center bg-black text-white">
                    Loading...
                </div>
            )}
        </AuthContext.Provider>
    )
}
