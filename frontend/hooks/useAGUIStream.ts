import { useState, useCallback, useRef, useEffect } from 'react';
import { useUser } from '@/lib/contexts/UserContext';
import { useProject } from '@/lib/contexts/ProjectContext';
import { GanttChartData, GanttPanelState } from '@/types/schedule';

export type Message = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
    responseType?: 'success' | 'clarification' | 'error';  // Structured response type
    options?: string[];  // For clarification responses
};

export type AgentState = {
    node: string;
    status: 'working' | 'completed' | 'error';
    intent?: string;
    reasoning?: string;
};

export interface ConversationMetadata {
    id: string;
    isNew: boolean;
    isSaved: boolean;
    title?: string;
}

// SSE Event Types from backend
type SSETokenEvent = { type: 'token'; content: string };
type SSEReasoningEvent = { type: 'reasoning'; node: string; content: string };
type SSENodeEvent = { node: string; status: string; intent?: string };
type SSEEndEvent = { node: 'End'; output: string };
type SSEErrorEvent = { node: 'Error'; status: 'error'; error: string };
type SSEGanttPanelEvent = { type: 'gantt_panel'; action: 'show' | 'hide'; data?: GanttChartData };
type SSEEvent = SSETokenEvent | SSEReasoningEvent | SSENodeEvent | SSEEndEvent | SSEErrorEvent | SSEGanttPanelEvent;

function isTokenEvent(data: SSEEvent): data is SSETokenEvent {
    return 'type' in data && data.type === 'token';
}

function isReasoningEvent(data: SSEEvent): data is SSEReasoningEvent {
    return 'type' in data && data.type === 'reasoning';
}

function isEndEvent(data: SSEEvent): data is SSEEndEvent {
    return 'node' in data && data.node === 'End';
}

function isErrorEvent(data: SSEEvent): data is SSEErrorEvent {
    return 'node' in data && data.node === 'Error';
}

function isGanttPanelEvent(data: SSEEvent): data is SSEGanttPanelEvent {
    return 'type' in data && data.type === 'gantt_panel';
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
    const [ganttPanel, setGanttPanel] = useState<GanttPanelState>({
        isVisible: false,
        data: null,
        isLoading: false,
    });

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
            const response = await fetch('http://localhost:8500/api/v1/chat', {
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

            const assistantMessageId = crypto.randomUUID();

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

            // Buffer for incomplete SSE messages across chunks
            let sseBuffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                // Append new chunk to buffer
                sseBuffer += chunk;
                
                // Split by SSE message delimiter
                const messages = sseBuffer.split('\n\n');
                
                // Keep the last (possibly incomplete) message in buffer
                sseBuffer = messages.pop() || '';

                for (const line of messages) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (!dataStr) continue; // Skip empty data
                        try {
                            const data: SSEEvent = JSON.parse(dataStr);

                            if (isTokenEvent(data)) {
                                // Streaming token from agent
                                setMessages((prev) =>
                                    prev.map((msg) =>
                                        msg.id === assistantMessageId
                                            ? { ...msg, content: msg.content + data.content }
                                            : msg
                                    )
                                );
                            } else if (isReasoningEvent(data)) {
                                // Agent is thinking/reasoning
                                setAgentState((prev) => ({
                                    node: data.node || prev?.node || 'Processing',
                                    status: 'working',
                                    intent: prev?.intent,
                                    reasoning: (prev?.reasoning || '') + data.content
                                }));
                            } else if (isEndEvent(data)) {
                                // Stream complete
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
                            } else if (isErrorEvent(data)) {
                                // Error from agent
                                setAgentState({ node: 'Error', status: 'error' });
                                setMessages((prev) =>
                                    prev.map((msg) =>
                                        msg.id === assistantMessageId
                                            ? { ...msg, content: data.error, responseType: 'error' }
                                            : msg
                                    )
                                );
                            } else if (isGanttPanelEvent(data)) {
                                // Gantt panel show/hide event
                                if (data.action === 'show' && data.data) {
                                    setGanttPanel({
                                        isVisible: true,
                                        data: data.data,
                                        isLoading: false,
                                    });
                                } else if (data.action === 'hide') {
                                    setGanttPanel({
                                        isVisible: false,
                                        data: null,
                                        isLoading: false,
                                    });
                                }
                            } else {
                                // Node status update
                                setAgentState((prev) => ({
                                    node: data.node,
                                    status: data.status as 'working' | 'completed' | 'error',
                                    intent: data.intent,
                                    reasoning: prev?.reasoning,
                                }));
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data', e);
                        }
                    }
                }
            }
        } catch (error: unknown) {
            if (error instanceof Error && error.name !== 'AbortError') {
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
        setGanttPanel({ isVisible: false, data: null, isLoading: false });

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

    const hideGanttPanel = useCallback(() => {
        setGanttPanel({ isVisible: false, data: null, isLoading: false });
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
        // Gantt panel state and handlers
        ganttPanel,
        hideGanttPanel,
    };
}
