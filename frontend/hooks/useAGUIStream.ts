import { useState, useCallback, useRef, useEffect } from 'react';
import { useUser } from '@/lib/contexts/UserContext';
import { useProject } from '@/lib/contexts/ProjectContext';

export type Message = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
};

export type AgentState = {
    node: string;
    status: string;
    intent?: string;
    reasoning?: string;
};

export interface ConversationMetadata {
    id: string;
    isNew: boolean;
    isSaved: boolean;
    title?: string;
}

export function useAGUIStream() {
    const { user } = useUser();
    const { currentProject } = useProject();
    const [messages, setMessages] = useState<Message[]>([]);
    const [agentState, setAgentState] = useState<AgentState | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const conversationIdRef = useRef<string>('');
    const abortControllerRef = useRef<AbortController | null>(null);
    const [conversationMetadata, setConversationMetadata] = useState<ConversationMetadata | null>(null);

    useEffect(() => {
        // Initialize conversation ID on client side only
        if (typeof window !== 'undefined') {
            const newId = crypto.randomUUID();
            conversationIdRef.current = newId;
            setConversationMetadata({
                id: newId,
                isNew: true,
                isSaved: false
            });
        }
    }, []);

    const sendMessage = useCallback(async (content: string) => {
        if (!content.trim()) return;

        const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'user',
            content,
            timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setIsLoading(true);
        setAgentState({ node: 'Starting', status: 'working' });

        abortControllerRef.current = new AbortController();

        try {
            // Bypass Next.js proxy and hit backend directly to avoid buffering
            const response = await fetch('http://localhost:8400/api/v1/graph/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(currentProject ? { 'Lognos-ProjectID': currentProject.project_id } : {}),
                },
                body: JSON.stringify({
                    message: content,
                    sender_email: user?.email || 'anonymous@lognos.io',
                    conversation_id: conversationIdRef.current,
                }),
                signal: abortControllerRef.current.signal,
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) return;

            let assistantMessageId = crypto.randomUUID();

            // Add placeholder assistant message
            setMessages((prev) => [
                ...prev,
                {
                    id: assistantMessageId,
                    role: 'assistant',
                    content: '',
                    timestamp: Date.now(),
                },
            ]);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        try {
                            const data = JSON.parse(dataStr);

                            if (data.type === 'token') {
                                setMessages((prev) =>
                                    prev.map((msg) =>
                                        msg.id === assistantMessageId
                                            ? { ...msg, content: msg.content + data.content }
                                            : msg
                                    )
                                );
                            } else if (data.type === 'reasoning') {
                                setAgentState((prev) => ({
                                    node: data.node || prev?.node || 'Processing',
                                    status: 'working',
                                    intent: prev?.intent,
                                    reasoning: (prev?.reasoning || '') + data.content
                                }));
                            } else if (data.node === 'End') {
                                setAgentState(null);
                                if (data.output) {
                                    setMessages((prev) =>
                                        prev.map((msg) =>
                                            msg.id === assistantMessageId
                                                ? { ...msg, content: data.output }
                                                : msg
                                        )
                                    );
                                }
                            } else {
                                setAgentState((prev) => ({
                                    node: data.node,
                                    status: data.status,
                                    intent: data.intent,
                                    reasoning: prev?.reasoning,
                                }));

                                if (data.final_response) {
                                    setMessages((prev) =>
                                        prev.map((msg) =>
                                            msg.id === assistantMessageId
                                                ? { ...msg, content: data.final_response }
                                                : msg
                                        )
                                    );
                                }
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data', e);
                        }
                    }
                }
            }
        } catch (error: any) {
            if (error.name !== 'AbortError') {
                console.error('Stream error:', error);
            }
        } finally {
            setIsLoading(false);
            setAgentState(null);
            abortControllerRef.current = null;
            // Mark conversation as saved after successful message
            setConversationMetadata(prev =>
                prev ? { ...prev, isSaved: true } : null
            );
        }
    }, [user?.email, currentProject]);

    const resetConversation = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setMessages([]);
        setAgentState(null);
        setIsLoading(false);

        const newId = crypto.randomUUID();
        conversationIdRef.current = newId;
        setConversationMetadata({
            id: newId,
            isNew: true,
            isSaved: false
        });
    }, []);

    const loadConversation = useCallback((conversationId: string, existingMessages: Message[]) => {
        conversationIdRef.current = conversationId;
        setMessages(existingMessages);
        setConversationMetadata({
            id: conversationId,
            isNew: false,
            isSaved: true
        });
    }, []);

    return {
        messages,
        sendMessage,
        agentState,
        isLoading,
        resetConversation,
        loadConversation,
        conversationMetadata,
        isDirty: conversationMetadata?.isSaved === false,
    };
}
