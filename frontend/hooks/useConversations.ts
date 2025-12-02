import { useState, useCallback, useRef } from 'react';
import {
    ConversationNotFoundError,
    ConversationLoadError,
    UnauthorizedConversationError,
    NetworkError,
} from '@/types/conversation-errors';
import { useProject } from '@/lib/contexts/ProjectContext';

export interface ConversationSummary {
    conversation_id: string;
    title: string;
    last_message_at: string | null;
    message_count: number;
    status: string;
}

interface CacheEntry {
    data: ConversationSummary[];
    timestamp: number;
}

export function useConversations(userEmail: string) {
    const { currentProject } = useProject();
    const [conversations, setConversations] = useState<ConversationSummary[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Cache with 30s TTL
    const cacheRef = useRef<CacheEntry | null>(null);
    const CACHE_TTL = 30000; // 30 seconds

    const fetchConversations = useCallback(async (force = false) => {
        const now = Date.now();

        // Return cached data if valid
        if (!force && cacheRef.current && (now - cacheRef.current.timestamp < CACHE_TTL)) {
            setConversations(cacheRef.current.data);
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch(
                `http://localhost:8500/api/v1/conversations?user_email=${encodeURIComponent(userEmail)}`,
                {
                    headers: {
                        ...(currentProject ? { 'Lognos-ProjectID': currentProject.project_id } : {}),
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const newData = data.conversations;

            setConversations(newData);
            cacheRef.current = { data: newData, timestamp: now };
        } catch (err) {
            const errorMsg = err instanceof Error ? err.message : 'Unknown error';
            setError(errorMsg);
            console.error('Failed to fetch conversations:', err);
        } finally {
            setIsLoading(false);
        }
    }, [userEmail, currentProject]);

    const hideConversation = useCallback(async (id: string) => {
        // Optimistic update
        const previousConversations = conversations;
        setConversations(prev => prev.filter(c => c.conversation_id !== id));

        try {
            const response = await fetch(`http://localhost:8500/api/v1/conversations/${id}?user_email=${encodeURIComponent(userEmail)}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    ...(currentProject ? { 'Lognos-ProjectID': currentProject.project_id } : {}),
                },
                body: JSON.stringify({ visible: false }),
            });

            if (!response.ok) {
                throw new Error('Failed to hide conversation');
            }

            // Invalidate cache
            cacheRef.current = null;
        } catch (err) {
            // Roll back on error
            setConversations(previousConversations);
            setError(err instanceof Error ? err.message : 'Unknown error');
            console.error('Failed to hide conversation:', err);
        }
    }, [conversations, userEmail, currentProject]);

    const loadConversation = useCallback(async (id: string) => {
        try {
            const response = await fetch(
                `http://localhost:8500/api/v1/conversations/${id}?user_email=${encodeURIComponent(userEmail)}`,
                {
                    headers: {
                        ...(currentProject ? { 'Lognos-ProjectID': currentProject.project_id } : {}),
                    }
                }
            );

            if (response.status === 404) {
                throw new ConversationNotFoundError(id);
            }
            if (response.status === 403) {
                throw new UnauthorizedConversationError();
            }
            if (!response.ok) {
                throw new ConversationLoadError(`HTTP ${response.status}`);
            }

            const data = await response.json();
            return data.messages;
        } catch (error) {
            if (
                error instanceof ConversationNotFoundError ||
                error instanceof UnauthorizedConversationError ||
                error instanceof ConversationLoadError
            ) {
                throw error;
            }
            throw new NetworkError(error as Error);
        }
    }, [userEmail, currentProject]);

    return {
        conversations,
        isLoading,
        error,
        fetchConversations,
        hideConversation,
        loadConversation,
        invalidateCache: () => { cacheRef.current = null; },
    };
}
