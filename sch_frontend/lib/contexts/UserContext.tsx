"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { UserContextType, UserPreferences } from '@/types/user';
import { translations, SupportedLanguage, TranslationKey } from '@/lib/i18n';
import { useAuth } from '@/components/providers/AuthProvider';

interface UserContextState {
    user: UserContextType | null;
    isLoading: boolean;
    error: string | null;
    updatePreferences: (prefs: Partial<UserPreferences>) => Promise<void>;
    refreshUser: () => Promise<void>;
    t: (key: TranslationKey) => string;
}

const UserContext = createContext<UserContextState | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
    const { user: authUser, loading: authLoading } = useAuth();
    const [user, setUser] = useState<UserContextType | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchUser = async () => {
        try {
            setIsLoading(true);

            if (!authUser) {
                setUser(null);
                return;
            }

            // Map AuthUser to UserContextType
            setUser({
                user_id: authUser.id,
                email: authUser.email,
                full_name: authUser.user_name,
                first_name: authUser.first_name || authUser.user_name.split(' ')[0],
                roles: [authUser.user_role],
                preferences: {
                    theme: 'system',
                    language: authUser.preferred_language || 'en',
                    notifications_enabled: true
                },
                display_name: authUser.user_name
            });

        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch user');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (!authLoading) {
            fetchUser();
        }
    }, [authUser, authLoading]);

    const updatePreferences = async (prefs: Partial<UserPreferences>) => {
        if (!user) return;

        try {
            // Optimistic update
            const newPrefs = { ...user.preferences, ...prefs };
            setUser({ ...user, preferences: newPrefs });

            // API call
            await fetch(`/api/v1/user/${user.user_id}/preferences`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newPrefs)
            });
        } catch (err) {
            // Revert on error?
            console.error("Failed to update preferences", err);
            fetchUser(); // Refresh to get true state
        }
    };

    const t = (key: TranslationKey): string => {
        const lang = (user?.preferences.language || 'en') as SupportedLanguage;
        // @ts-ignore - simple fallback
        return translations[lang]?.[key] || translations['en'][key] || key;
    };

    return (
        <UserContext.Provider value={{ user, isLoading, error, updatePreferences, refreshUser: fetchUser, t }}>
            {children}
        </UserContext.Provider>
    );
}

export function useUser() {
    const context = useContext(UserContext);
    if (context === undefined) {
        throw new Error('useUser must be used within a UserProvider');
    }
    return context;
}
