import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GripHorizontal } from 'lucide-react';
import { Message, AgentState } from '@/hooks/useAGUIStream';
import { MessageBubble } from './MessageBubble';
import { ThinkingIndicator } from './ThinkingIndicator';
import { InputArea } from './InputArea';
import { Sidebar } from './Sidebar';
import { SAChatHeader } from './SAChatHeader';
import { SAGanttPanel } from './gantt';
import { useUser } from '@/lib/contexts/UserContext';
import { GanttPanelState, ScheduleViewKey, ScheduleViewMeta, BaselineMode } from '@/types/schedule';
import {
    SAWorkspaceMode,
    SAEffectiveMode,
    SADockedMode,
    SAShellMode,
    SAWorkspaceLayoutActions,
    FloatingChatGeometry,
} from '@/types/workspace';

interface SAWorkspaceProps {
    messages: Message[];
    agentState: AgentState | null;
    isLoading: boolean;
    onSendMessage: (content: string) => void;
    onNewConversation: () => void;
    onHistoryToggle: () => void;
    ganttPanel?: GanttPanelState;
    onHideGanttPanel?: () => void;
    scheduleViews?: ScheduleViewMeta[];
    activeScheduleViewKey?: ScheduleViewKey | null;
    onSelectScheduleView?: (viewKey: ScheduleViewKey) => void;
    onBaselineModeChange?: (mode: BaselineMode) => void;
    isPreloadingSchedule?: boolean;
    /** 'standalone' renders the local Sidebar + ProjectSelector. 'embedded' defers to the host. */
    shellMode?: SAShellMode;
    /** localStorage key prefix; allows multiple host embeddings to coexist. */
    persistenceNamespace?: string;
}

const DEFAULT_NAMESPACE = 'lognos.sa.workspace';
const GANTT_MIN_WIDTH = 620;
const SIDEBAR_OFFSET_PX = 64; // matches Sidebar collapsed width (w-16)
const FLOAT_MIN_WIDTH = 360;
const FLOAT_MIN_HEIGHT = 280;
const FLOAT_MARGIN = 24;

const DEFAULT_FLOATING_CHAT: FloatingChatGeometry = {
    x: 80,
    y: 80,
    width: 480,
    height: 560,
};

function clampGeometry(
    geom: FloatingChatGeometry,
    bounds: { width: number; height: number }
): FloatingChatGeometry {
    const width = Math.min(Math.max(geom.width, FLOAT_MIN_WIDTH), Math.max(FLOAT_MIN_WIDTH, bounds.width - FLOAT_MARGIN * 2));
    const height = Math.min(Math.max(geom.height, FLOAT_MIN_HEIGHT), Math.max(FLOAT_MIN_HEIGHT, bounds.height - FLOAT_MARGIN * 2));
    const x = Math.min(Math.max(geom.x, 0), Math.max(0, bounds.width - width));
    const y = Math.min(Math.max(geom.y, 0), Math.max(0, bounds.height - height));
    return { x, y, width, height };
}

/**
 * SAWorkspace — Schedule Assistant workspace shell.
 *
 * Owns layout mode state and renders:
 *   - Mode A 'gantt-full-chat-floating': Gantt fills the canvas; chat is a draggable floating panel
 *   - Mode B 'gantt-main-chat-side'    : Gantt left, chat right (resizable split)
 *   - Mode C 'chat-main-gantt-side'    : Chat left, Gantt right (legacy layout)
 *
 * Empty schedule fallback: when no Gantt data is available, the effective mode
 * is forced to chat-only ('chat-only-virtual'); the stored mode is preserved.
 */
export const SAWorkspace: React.FC<SAWorkspaceProps> = ({
    messages,
    agentState,
    isLoading,
    onSendMessage,
    onNewConversation,
    onHistoryToggle,
    ganttPanel,
    onHideGanttPanel,
    scheduleViews,
    activeScheduleViewKey,
    onSelectScheduleView,
    onBaselineModeChange,
    isPreloadingSchedule,
    shellMode = 'standalone',
    persistenceNamespace = DEFAULT_NAMESPACE,
}) => {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const workspaceRef = useRef<HTMLDivElement>(null);
    const { user, t } = useUser();

    // -- Layout state -------------------------------------------------------
    const storageKeys = useMemo(() => ({
        mode: `${persistenceNamespace}.layoutMode`,
        floatingChat: `${persistenceNamespace}.floatingChat`,
        splitRatio: `${persistenceNamespace}.splitRatio`,
        ganttWidth: `${persistenceNamespace}.ganttWidth`,
        lastDocked: `${persistenceNamespace}.lastDockedMode`,
    }), [persistenceNamespace]);

    const validModes: SAWorkspaceMode[] = ['gantt-full-chat-floating', 'gantt-main-chat-side', 'chat-main-gantt-side'];
    const validDocked: SADockedMode[] = ['gantt-main-chat-side', 'chat-main-gantt-side'];

    const readStored = <T,>(key: string, parse: (raw: string) => T | null): T | null => {
        if (typeof window === 'undefined') return null;
        try {
            const raw = window.localStorage.getItem(key);
            if (raw === null) return null;
            return parse(raw);
        } catch {
            return null;
        }
    };

    const [layoutMode, setLayoutMode] = useState<SAWorkspaceMode>(() =>
        readStored<SAWorkspaceMode>(storageKeys.mode, (raw) =>
            validModes.includes(raw as SAWorkspaceMode) ? (raw as SAWorkspaceMode) : null,
        ) ?? 'gantt-main-chat-side'
    );
    const [lastDockedMode, setLastDockedMode] = useState<SADockedMode>(() =>
        readStored<SADockedMode>(storageKeys.lastDocked, (raw) =>
            validDocked.includes(raw as SADockedMode) ? (raw as SADockedMode) : null,
        ) ?? 'gantt-main-chat-side'
    );
    const [ganttSideWidth, setGanttSideWidth] = useState<number>(() =>
        readStored<number>(storageKeys.ganttWidth, (raw) => {
            const n = Number(raw);
            return Number.isFinite(n) && n >= GANTT_MIN_WIDTH ? n : null;
        }) ?? 900
    );
    const [splitRatio, setSplitRatio] = useState<number>(() =>
        readStored<number>(storageKeys.splitRatio, (raw) => {
            const n = Number(raw);
            return Number.isFinite(n) && n > 0.05 && n < 0.95 ? n : null;
        }) ?? 0.2
    );
    const [floatingChat, setFloatingChat] = useState<FloatingChatGeometry>(() =>
        readStored<FloatingChatGeometry>(storageKeys.floatingChat, (raw) => {
            try {
                const parsed = JSON.parse(raw);
                if (
                    parsed &&
                    typeof parsed.x === 'number' &&
                    typeof parsed.y === 'number' &&
                    typeof parsed.width === 'number' &&
                    typeof parsed.height === 'number'
                ) {
                    return parsed as FloatingChatGeometry;
                }
                return null;
            } catch {
                return null;
            }
        }) ?? DEFAULT_FLOATING_CHAT
    );

    // Persist on change.
    useEffect(() => {
        if (typeof window === 'undefined') return;
        try { window.localStorage.setItem(storageKeys.mode, layoutMode); } catch { /* ignore */ }
    }, [layoutMode, storageKeys.mode]);
    useEffect(() => {
        if (typeof window === 'undefined') return;
        try { window.localStorage.setItem(storageKeys.lastDocked, lastDockedMode); } catch { /* ignore */ }
    }, [lastDockedMode, storageKeys.lastDocked]);
    useEffect(() => {
        if (typeof window === 'undefined') return;
        try { window.localStorage.setItem(storageKeys.ganttWidth, String(ganttSideWidth)); } catch { /* ignore */ }
    }, [ganttSideWidth, storageKeys.ganttWidth]);
    useEffect(() => {
        if (typeof window === 'undefined') return;
        try { window.localStorage.setItem(storageKeys.splitRatio, String(splitRatio)); } catch { /* ignore */ }
    }, [splitRatio, storageKeys.splitRatio]);
    useEffect(() => {
        if (typeof window === 'undefined') return;
        try { window.localStorage.setItem(storageKeys.floatingChat, JSON.stringify(floatingChat)); } catch { /* ignore */ }
    }, [floatingChat, storageKeys.floatingChat]);

    // -- Effective mode (empty-schedule fallback) ---------------------------
    const isGanttVisible = !!(ganttPanel?.isVisible && ganttPanel?.data);
    const effectiveMode: SAEffectiveMode = isGanttVisible ? layoutMode : 'chat-only-virtual';

    // -- Layout actions -----------------------------------------------------
    const layoutActions = useMemo<SAWorkspaceLayoutActions>(() => ({
        pinChatRight: () => {
            setLayoutMode('gantt-main-chat-side');
            setLastDockedMode('gantt-main-chat-side');
        },
        unpinChatToFloating: () => {
            // Remember the current docked mode so a future re-pin can restore it.
            if (layoutMode === 'gantt-main-chat-side' || layoutMode === 'chat-main-gantt-side') {
                setLastDockedMode(layoutMode);
            }
            setLayoutMode('gantt-full-chat-floating');
        },
        makeGanttFull: () => {
            if (layoutMode === 'gantt-main-chat-side' || layoutMode === 'chat-main-gantt-side') {
                setLastDockedMode(layoutMode);
            }
            setLayoutMode('gantt-full-chat-floating');
        },
        makeSplit: () => {
            // Restore the user's last docked layout (default Mode B).
            setLayoutMode(lastDockedMode);
        },
        swapSides: () => {
            setLayoutMode((prev) => {
                if (prev === 'gantt-main-chat-side') return 'chat-main-gantt-side';
                if (prev === 'chat-main-gantt-side') return 'gantt-main-chat-side';
                return prev;
            });
            setLastDockedMode((prev) => prev === 'gantt-main-chat-side' ? 'chat-main-gantt-side' : 'gantt-main-chat-side');
        },
    }), [layoutMode, lastDockedMode]);

    // -- Gantt width clamp (used for dockedRight / dockedLeft) -------------
    const handleGanttWidthChange = useCallback((nextWidth: number) => {
        const maxWidth = typeof window === 'undefined'
            ? 1400
            : Math.max(GANTT_MIN_WIDTH, window.innerWidth - 220);
        setGanttSideWidth(Math.min(Math.max(nextWidth, GANTT_MIN_WIDTH), maxWidth));
    }, []);

    // -- Floating chat drag ------------------------------------------------
    const dragStateRef = useRef<{
        startMouseX: number;
        startMouseY: number;
        startX: number;
        startY: number;
    } | null>(null);

    const startFloatingDrag = (event: React.MouseEvent<HTMLDivElement>) => {
        // Ignore drag when the click target is interactive (button etc).
        if ((event.target as HTMLElement).closest('button, a, input, textarea')) return;
        event.preventDefault();
        dragStateRef.current = {
            startMouseX: event.clientX,
            startMouseY: event.clientY,
            startX: floatingChat.x,
            startY: floatingChat.y,
        };
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'grabbing';
    };

    useEffect(() => {
        const onMove = (event: MouseEvent) => {
            const drag = dragStateRef.current;
            if (!drag) return;
            const rect = workspaceRef.current?.getBoundingClientRect();
            const bounds = rect
                ? { width: rect.width, height: rect.height }
                : { width: window.innerWidth, height: window.innerHeight };
            const dx = event.clientX - drag.startMouseX;
            const dy = event.clientY - drag.startMouseY;
            setFloatingChat((prev) => clampGeometry(
                { ...prev, x: drag.startX + dx, y: drag.startY + dy },
                bounds,
            ));
        };
        const onUp = () => {
            if (!dragStateRef.current) return;
            dragStateRef.current = null;
            document.body.style.removeProperty('user-select');
            document.body.style.removeProperty('cursor');
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
    }, []);

    // Re-clamp floating chat when the workspace bounds change.
    useEffect(() => {
        const onResize = () => {
            const rect = workspaceRef.current?.getBoundingClientRect();
            if (!rect) return;
            setFloatingChat((prev) => clampGeometry(prev, { width: rect.width, height: rect.height }));
        };
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    // -- Split-divider drag (Mode B / Mode C) ------------------------------
    const splitDragRef = useRef<{ startX: number; startRatio: number; orientation: 'gantt-left' | 'gantt-right' } | null>(null);

    const startSplitDrag = (
        event: React.MouseEvent<HTMLDivElement>,
        orientation: 'gantt-left' | 'gantt-right',
    ) => {
        event.preventDefault();
        splitDragRef.current = { startX: event.clientX, startRatio: splitRatio, orientation };
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
    };

    useEffect(() => {
        const onMove = (event: MouseEvent) => {
            const drag = splitDragRef.current;
            if (!drag) return;
            const rect = workspaceRef.current?.getBoundingClientRect();
            if (!rect) return;
            const totalWidth = rect.width - (shellMode === 'standalone' ? SIDEBAR_OFFSET_PX : 0);
            if (totalWidth <= 0) return;
            const dx = event.clientX - drag.startX;
            // splitRatio always represents the *chat-side* width fraction.
            // - 'gantt-left' : chat is on the right; dragging right shrinks chat (negative delta)
            // - 'gantt-right': chat is on the left;  dragging right grows chat
            const deltaRatio = (drag.orientation === 'gantt-left' ? -dx : dx) / totalWidth;
            const next = Math.min(Math.max(drag.startRatio + deltaRatio, 0.1), 0.7);
            setSplitRatio(next);
        };
        const onUp = () => {
            if (!splitDragRef.current) return;
            splitDragRef.current = null;
            document.body.style.removeProperty('user-select');
            document.body.style.removeProperty('cursor');
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
    }, [shellMode]);

    // -- Auto-scroll messages ----------------------------------------------
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, agentState]);

    // -- Render helpers ----------------------------------------------------
    const sidebarOffsetClass = shellMode === 'standalone' ? 'pl-16' : '';

    const renderChatBody = (variant: 'docked' | 'floating') => (
        <main className={`flex-1 overflow-y-auto p-4 ${variant === 'docked' ? 'sm:p-6' : ''} scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent`}>
            <div className={`${variant === 'docked' ? 'max-w-5xl' : ''} mx-auto flex flex-col space-y-8 pb-4 pt-8 min-h-full`}>
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center flex-1 h-[60vh] text-center space-y-8">
                        <div className="space-y-4">
                            <p className={`${variant === 'docked' ? 'text-4xl' : 'text-2xl'} text-gray-300 font-light`}>
                                {t('greeting')}, {user?.first_name || 'User'}.
                            </p>
                        </div>
                        <div className="w-full max-w-3xl">
                            <InputArea onSend={onSendMessage} disabled={isLoading} />
                        </div>
                    </div>
                ) : (
                    <>
                        {messages.map((msg) => (
                            <MessageBubble key={msg.id} message={msg} />
                        ))}
                        {agentState && <ThinkingIndicator state={agentState} />}
                    </>
                )}
                <div ref={messagesEndRef} />
            </div>
        </main>
    );

    const renderChatFooterInput = () => (
        messages.length > 0 ? (
            <footer className="flex-none bg-[#0d1117] pb-8 pt-4 px-4">
                <InputArea onSend={onSendMessage} disabled={isLoading} />
            </footer>
        ) : null
    );

    // -- Layout-specific renders -------------------------------------------

    // Mode A: Gantt full + floating chat
    const renderGanttFullChatFloating = () => (
        <div className={`flex-1 flex flex-col min-h-0 ${sidebarOffsetClass} relative`}>
            {/* Gantt fills the canvas */}
            {ganttPanel?.data && (
                <div className="flex-1 min-h-0 p-4 flex flex-col">
                    <SAGanttPanel
                        data={ganttPanel.data}
                        onClose={onHideGanttPanel ?? (() => {})}
                        width={ganttSideWidth}
                        onWidthChange={handleGanttWidthChange}
                        availableViews={scheduleViews || []}
                        activeViewKey={activeScheduleViewKey || undefined}
                        onSelectView={onSelectScheduleView}
                        onBaselineModeChange={onBaselineModeChange}
                        isViewLoading={isPreloadingSchedule}
                        variant="full"
                        shellMode={shellMode}
                        layoutMode={layoutMode}
                        layoutActions={layoutActions}
                    />
                </div>
            )}

            {/* Floating chat panel */}
            <div
                className="absolute bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl flex flex-col overflow-hidden z-40"
                style={{
                    left: `${floatingChat.x}px`,
                    top: `${floatingChat.y}px`,
                    width: `${floatingChat.width}px`,
                    height: `${floatingChat.height}px`,
                }}
            >
                {/* Drag handle strip */}
                <div
                    onMouseDown={startFloatingDrag}
                    className="flex items-center justify-center px-2 py-1 border-b border-dark-700 bg-[#0d1117]/90 cursor-grab active:cursor-grabbing select-none"
                    title="Drag to move"
                >
                    <GripHorizontal className="h-4 w-4 text-gray-500" />
                </div>
                <SAChatHeader
                    onHistoryToggle={onHistoryToggle}
                    onNewConversation={onNewConversation}
                    layoutMode={layoutMode}
                    layoutActions={layoutActions}
                    showProjectSelector={shellMode === 'standalone'}
                />
                {renderChatBody('floating')}
                {renderChatFooterInput()}
            </div>
        </div>
    );

    // Mode B / Mode C: docked split
    const renderDockedSplit = (mode: SADockedMode) => {
        const ganttOnLeft = mode === 'gantt-main-chat-side';
        const chatFlex = `${splitRatio}`;
        const ganttFlex = `${1 - splitRatio}`;

        const chatColumn = (
            <div className="flex flex-col min-w-0 min-h-0 h-full" style={{ flex: chatFlex }}>
                <SAChatHeader
                    onHistoryToggle={onHistoryToggle}
                    onNewConversation={onNewConversation}
                    layoutMode={layoutMode}
                    layoutActions={layoutActions}
                    showProjectSelector={shellMode === 'standalone'}
                />
                {renderChatBody('docked')}
                {renderChatFooterInput()}
            </div>
        );

        const ganttColumn = ganttPanel?.data ? (
            <div className="relative min-w-0 min-h-0 h-full p-4 flex flex-col" style={{ flex: ganttFlex }}>
                <SAGanttPanel
                    data={ganttPanel.data}
                    onClose={onHideGanttPanel ?? (() => {})}
                    width={ganttSideWidth}
                    onWidthChange={handleGanttWidthChange}
                    availableViews={scheduleViews || []}
                    activeViewKey={activeScheduleViewKey || undefined}
                    onSelectView={onSelectScheduleView}
                    onBaselineModeChange={onBaselineModeChange}
                    isViewLoading={isPreloadingSchedule}
                    variant="full"
                    shellMode={shellMode}
                    layoutMode={layoutMode}
                    layoutActions={layoutActions}
                />
            </div>
        ) : null;

        const divider = (
            <div
                className="w-1 cursor-col-resize bg-dark-700 hover:bg-blue-500/40 transition-colors"
                onMouseDown={(e) => startSplitDrag(e, ganttOnLeft ? 'gantt-left' : 'gantt-right')}
                aria-hidden="true"
            />
        );

        return (
            <div className={`flex-1 flex min-h-0 ${sidebarOffsetClass}`}>
                {ganttOnLeft ? (
                    <>
                        {ganttColumn}
                        {ganttColumn && divider}
                        {chatColumn}
                    </>
                ) : (
                    <>
                        {chatColumn}
                        {ganttColumn && divider}
                        {ganttColumn}
                    </>
                )}
            </div>
        );
    };

    // Empty schedule fallback: chat-only render, layout mode preserved.
    const renderChatOnly = () => (
        <div className={`flex-1 flex flex-col ${sidebarOffsetClass}`}>
            <SAChatHeader
                onHistoryToggle={onHistoryToggle}
                onNewConversation={onNewConversation}
                layoutMode={layoutMode}
                layoutActions={layoutActions}
                showProjectSelector={shellMode === 'standalone'}
            />
            {renderChatBody('docked')}
            {renderChatFooterInput()}
        </div>
    );

    return (
        <div
            ref={workspaceRef}
            className="relative flex h-screen bg-[#0d1117] text-white/90 font-light overflow-hidden"
        >
            {shellMode === 'standalone' && <Sidebar />}

            {effectiveMode === 'gantt-full-chat-floating' && renderGanttFullChatFloating()}
            {effectiveMode === 'gantt-main-chat-side' && renderDockedSplit('gantt-main-chat-side')}
            {effectiveMode === 'chat-main-gantt-side' && renderDockedSplit('chat-main-gantt-side')}
            {effectiveMode === 'chat-only-virtual' && renderChatOnly()}
        </div>
    );
};
