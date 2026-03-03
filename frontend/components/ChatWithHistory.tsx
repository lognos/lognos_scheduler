'use client';

import { useState, useRef, useCallback } from 'react';
import { ChatLayout } from '@/components/ChatLayout';
import { ConversationHistoryPanel } from '@/components/ConversationHistoryPanel';
import { useAGUIStream, Message } from '@/hooks/useAGUIStream';
import { useUser } from '@/lib/contexts/UserContext';
import {
    ConversationNotFoundError,
    UnauthorizedConversationError,
    NetworkError,
} from '@/types/conversation-errors';

/**
 * Wrapper component that handles conversation history logic.
 * Keeps ChatLayout focused on message display only.
 */
export function ChatWithHistory() {
    const { user } = useUser();
    const [showHistory, setShowHistory] = useState(false);
    const lastFetchRef = useRef<number>(0);

    const {
        messages,
        sendMessage,
        agentState,
        isLoading,
        resetConversation,
        loadConversation,
        conversationMetadata,
        ganttPanel,
        hideGanttPanel,
        scheduleViews,
        activeScheduleViewKey,
        switchScheduleView,
        isPreloadingSchedule,
    } = useAGUIStream();

    // Debounce panel toggle to prevent rapid fetches
    const MIN_FETCH_INTERVAL = 1000; // 1 second

    const handleHistoryToggle = useCallback(() => {
        setShowHistory(prev => {
            const now = Date.now();
            if (!prev && now - lastFetchRef.current > MIN_FETCH_INTERVAL) {
                lastFetchRef.current = now;
            }
            return !prev;
        });
    }, []);

    const handleSelectConversation = async (conversationId: string) => {
        try {
            // Fetch messages via API
            const response = await fetch(
                `http://localhost:8500/api/v1/conversations/${conversationId}?user_email=${encodeURIComponent(user?.email || '')}`
            );

            if (response.status === 404) {
                throw new ConversationNotFoundError(conversationId);
            }
            if (response.status === 403) {
                throw new UnauthorizedConversationError();
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            type ConversationApiMessage = {
                message_id: string;
                role: string;
                content: string;
                timestamp: string;
            };

            const messages: Message[] = (data.messages as ConversationApiMessage[]).map((msg) => ({
                id: msg.message_id,
                role: msg.role === 'user' ? 'user' : 'assistant',
                content: msg.content,
                timestamp: new Date(msg.timestamp).getTime(),
            }));

            // Load into stream
            loadConversation(conversationId, messages);
            setShowHistory(false);
        } catch (error) {
            let errorMessage = 'Failed to load conversation';

            if (error instanceof ConversationNotFoundError) {
                errorMessage = 'This conversation no longer exists';
            } else if (error instanceof UnauthorizedConversationError) {
                errorMessage = 'You do not have access to this conversation';
            } else if (error instanceof NetworkError) {
                errorMessage = 'Network error. Please try again.';
            }

            console.error('Failed to load conversation:', error);
            alert(errorMessage); // TODO: Replace with toast notification
        }
    };

    return (
        <>
            <ChatLayout
                messages={messages}
                agentState={agentState}
                isLoading={isLoading}
                onSendMessage={sendMessage}
                onNewConversation={resetConversation}
                onHistoryToggle={handleHistoryToggle}
                ganttPanel={ganttPanel}
                onHideGanttPanel={hideGanttPanel}
                scheduleViews={scheduleViews}
                activeScheduleViewKey={activeScheduleViewKey}
                onSelectScheduleView={switchScheduleView}
                isPreloadingSchedule={isPreloadingSchedule}
            />

            {showHistory && (
                <ConversationHistoryPanel
                    isOpen={showHistory}
                    onClose={() => setShowHistory(false)}
                    onSelectConversation={handleSelectConversation}
                    currentConversationId={conversationMetadata?.id || null}
                    userEmail={user?.email || ''}
                />
            )}
        </>
    );
}
