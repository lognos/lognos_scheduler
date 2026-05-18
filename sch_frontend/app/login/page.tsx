'use client'

import React, { useState } from 'react'
import { useAuth } from '../../components/providers/AuthProvider'
import LognosLogo from '../../components/LognosLogo'

export default function LoginPage() {
    const { signInWithMicrosoft, loading } = useAuth()
    const [isSigningIn, setIsSigningIn] = useState(false)

    const handleMicrosoftSignIn = async () => {
        try {
            setIsSigningIn(true)
            await signInWithMicrosoft()
        } catch (error) {
            console.error('Sign in failed:', error)
            alert('Sign in failed. Please try again.')
        } finally {
            setIsSigningIn(false)
        }
    }

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-black">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
                    <p className="text-gray-400">Loading...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-black py-12 px-4 sm:px-6 lg:px-8">
            <div className="max-w-md w-full space-y-8">
                {/* Logo Section */}
                <div className="text-center">
                    <div className="flex items-center justify-center mb-8">
                        <LognosLogo
                            isExpanded={true}
                            size={32}
                            circleColor="#3B82F6"
                            textColor="#F9FAFB"
                        />
                    </div>
                </div>

                {/* Sign In Button */}
                <div className="mt-8">
                    <button
                        onClick={handleMicrosoftSignIn}
                        disabled={isSigningIn}
                        className="group relative w-full flex justify-center items-center py-4 px-6 border border-gray-600 text-sm font-medium rounded-lg text-white bg-gray-800/50 hover:bg-gray-700/50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 backdrop-blur-sm"
                    >
                        {isSigningIn ? (
                            <div className="flex items-center">
                                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-3"></div>
                                <span>Signing in...</span>
                            </div>
                        ) : (
                            <div className="flex items-center">
                                {/* Microsoft Logo */}
                                <svg className="w-5 h-5 mr-3" viewBox="0 0 23 23">
                                    <path fill="#f35325" d="M1 1h10v10H1z" />
                                    <path fill="#81bc06" d="M12 1h10v10H12z" />
                                    <path fill="#05a6f0" d="M1 12h10v10H1z" />
                                    <path fill="#ffba08" d="M12 12h10v10H12z" />
                                </svg>
                                <span
                                    style={{
                                        fontFamily: "'Helvetica Neue Light', 'Helvetica Neue', Helvetica, Arial, sans-serif",
                                        fontWeight: 300
                                    }}
                                >
                                    Sign in with Microsoft
                                </span>
                            </div>
                        )}
                    </button>
                </div>
            </div>
        </div>
    )
}
