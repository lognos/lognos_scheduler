import { useState, useCallback, useRef, useEffect } from 'react';
import { useUser } from '@/lib/contexts/UserContext';
import { useProject } from '@/lib/contexts/ProjectContext';
import {
    GanttChartData,
    GanttPanelState,
    ScheduleViewKey,
    ScheduleViewMeta,
    ScheduleViewsPreloadResponse,
    ScheduleViewResponse,
    BaselineMode,
} from '@/types/schedule';

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

const CUSTOM_VIEW_META: ScheduleViewMeta = {
    view_key: 'custom',
    view_name: 'Custom',
    view_type: 'session',
    is_default: false,
};

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
    const [scheduleViews, setScheduleViews] = useState<ScheduleViewMeta[]>([]);
    const [activeScheduleViewKey, setActiveScheduleViewKey] = useState<ScheduleViewKey | null>(null);
    const [isPreloadingSchedule, setIsPreloadingSchedule] = useState(false);
    const [scheduleViewCache, setScheduleViewCache] = useState<Record<string, GanttChartData>>({});

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

    useEffect(() => {
        let cancelled = false;

        const preloadScheduleViews = async () => {
            if (!currentProject?.project_id) {
                setScheduleViews([]);
                setActiveScheduleViewKey(null);
                setScheduleViewCache({});
                return;
            }

            setIsPreloadingSchedule(true);
            try {
                const response = await fetch('http://localhost:8500/api/v1/schedule-views/preload', {
                    headers: {
                        'Lognos-ProjectID': currentProject.project_id,
                    },
                });

                if (!response.ok) {
                    throw new Error(`Failed to preload schedule views (${response.status})`);
                }

                const data: ScheduleViewsPreloadResponse = await response.json();
                if (cancelled) return;

                const cache: Record<string, GanttChartData> = {};
                if (data.payload) {
                    cache[data.default_view_key] = data.payload;
                    setGanttPanel({
                        isVisible: true,
                        data: data.payload,
                        isLoading: false,
                    });
                }

                setScheduleViewCache(cache);
                setScheduleViews(data.views || []);
                setActiveScheduleViewKey(data.default_view_key);
            } catch (error) {
                if (!cancelled) {
                    console.error('Failed to preload schedule views', error);
                    setScheduleViews([]);
                    setActiveScheduleViewKey(null);
                    setScheduleViewCache({});
                }
            } finally {
                if (!cancelled) {
                    setIsPreloadingSchedule(false);
                }
            }
        };

        preloadScheduleViews();

        return () => {
            cancelled = true;
        };
    }, [currentProject?.project_id]);

    const switchScheduleView = useCallback(async (viewKey: ScheduleViewKey) => {
        if (!currentProject?.project_id) {
            return;
        }

        const cached = scheduleViewCache[viewKey];
        if (cached) {
            setActiveScheduleViewKey(viewKey);
            setGanttPanel({ isVisible: true, data: cached, isLoading: false });
            return;
        }

        if (viewKey === 'custom') {
            return;
        }

        setIsPreloadingSchedule(true);
        try {
            const response = await fetch(`http://localhost:8500/api/v1/schedule-views/${viewKey}`, {
                headers: {
                    'Lognos-ProjectID': currentProject.project_id,
                },
            });

            if (!response.ok) {
                throw new Error(`Failed to load view ${viewKey} (${response.status})`);
            }

            const data: ScheduleViewResponse = await response.json();
            if (!data.payload) {
                return;
            }

            setScheduleViewCache((prev) => ({ ...prev, [viewKey]: data.payload }));
            setActiveScheduleViewKey(viewKey);
            setGanttPanel({ isVisible: true, data: data.payload, isLoading: false });
        } catch (error) {
            console.error(`Failed to switch schedule view ${viewKey}`, error);
        } finally {
            setIsPreloadingSchedule(false);
        }
    }, [currentProject?.project_id, scheduleViewCache]);

    const switchBaselineMode = useCallback(async (mode: BaselineMode) => {
        if (!currentProject?.project_id) return;

        // Always re-fetch with the new baseline_mode (bypass cache)
        const viewKey = activeScheduleViewKey || 'full_schedule';
        if (viewKey === 'custom') return;

        setIsPreloadingSchedule(true);
        try {
            const url = `http://localhost:8500/api/v1/schedule-views/${viewKey}?baseline_mode=${mode}`;
            const response = await fetch(url, {
                headers: {
                    'Lognos-ProjectID': currentProject.project_id,
                },
            });

            if (!response.ok) {
                throw new Error(`Failed to switch baseline mode (${response.status})`);
            }

            const data: ScheduleViewResponse = await response.json();
            if (!data.payload) return;

            // Don't cache cross-version baselines (they depend on mode)
            if (mode === 'own') {
                setScheduleViewCache((prev) => ({ ...prev, [viewKey]: data.payload }));
            }
            setGanttPanel({ isVisible: true, data: data.payload, isLoading: false });
        } catch (error) {
            console.error(`Failed to switch baseline mode to ${mode}`, error);
        } finally {
            setIsPreloadingSchedule(false);
        }
    }, [currentProject?.project_id, activeScheduleViewKey]);

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
                    project_type: 'msp',
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
                                    const ganttData = data.data;
                                    setScheduleViewCache((prev) => ({ ...prev, custom: ganttData }));
                                    setScheduleViews((prev) => {
                                        const hasCustom = prev.some((view) => view.view_key === 'custom');
                                        if (hasCustom) {
                                            return prev.map((view) =>
                                                view.view_key === 'custom'
                                                    ? { ...view, computed_at: new Date().toISOString() }
                                                    : view
                                            );
                                        }

                                        return [...prev, { ...CUSTOM_VIEW_META, computed_at: new Date().toISOString() }];
                                    });
                                    setActiveScheduleViewKey('custom');
                                    setGanttPanel({
                                        isVisible: true,
                                        data: ganttData,
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
        scheduleViews,
        activeScheduleViewKey,
        switchScheduleView,
        switchBaselineMode,
        isPreloadingSchedule,
    };
}
