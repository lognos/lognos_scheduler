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

const PREVIOUS_DEFAULT_FLOATING_CHAT: FloatingChatGeometry = {
    x: 80,
    y: 80,
    width: 480,
    height: 560,
};

const DEFAULT_FLOATING_CHAT_SIZE = {
    width: 520,
    height: 560,
};

type FloatingResizeHandle = 'n' | 'e' | 's' | 'w' | 'ne' | 'nw' | 'se' | 'sw';

const FLOATING_RESIZE_HANDLES: Array<{
    handle: FloatingResizeHandle;
    className: string;
    label: string;
}> = [
    { handle: 'n', className: 'absolute left-4 right-4 top-0 h-2 cursor-ns-resize z-50', label: 'Resize chat from top edge' },
    { handle: 'e', className: 'absolute right-0 top-4 bottom-4 w-2 cursor-ew-resize z-50', label: 'Resize chat from right edge' },
    { handle: 's', className: 'absolute left-4 right-4 bottom-0 h-2 cursor-ns-resize z-50', label: 'Resize chat from bottom edge' },
    { handle: 'w', className: 'absolute left-0 top-4 bottom-4 w-2 cursor-ew-resize z-50', label: 'Resize chat from left edge' },
    { handle: 'ne', className: 'absolute right-0 top-0 h-4 w-4 cursor-nesw-resize z-50', label: 'Resize chat from top-right corner' },
    { handle: 'nw', className: 'absolute left-0 top-0 h-4 w-4 cursor-nwse-resize z-50', label: 'Resize chat from top-left corner' },
    { handle: 'se', className: 'absolute right-0 bottom-0 h-4 w-4 cursor-nwse-resize z-50', label: 'Resize chat from bottom-right corner' },
    { handle: 'sw', className: 'absolute left-0 bottom-0 h-4 w-4 cursor-nesw-resize z-50', label: 'Resize chat from bottom-left corner' },
];

function clampNumber(value: number, min: number, max: number): number {
    return Math.min(Math.max(value, min), max);
}

function clampGeometry(
    geom: FloatingChatGeometry,
    bounds: { width: number; height: number }
): FloatingChatGeometry {
    const maxWidth = Math.max(FLOAT_MIN_WIDTH, bounds.width - FLOAT_MARGIN * 2);
    const maxHeight = Math.max(FLOAT_MIN_HEIGHT, bounds.height - FLOAT_MARGIN * 2);
    const width = clampNumber(geom.width, FLOAT_MIN_WIDTH, maxWidth);
    const height = clampNumber(geom.height, FLOAT_MIN_HEIGHT, maxHeight);
    const maxX = Math.max(FLOAT_MARGIN, bounds.width - width - FLOAT_MARGIN);
    const maxY = Math.max(FLOAT_MARGIN, bounds.height - height - FLOAT_MARGIN);
    const x = clampNumber(geom.x, FLOAT_MARGIN, maxX);
    const y = clampNumber(geom.y, FLOAT_MARGIN, maxY);
    return { x, y, width, height };
}

function getDefaultFloatingChat(bounds: { width: number; height: number }): FloatingChatGeometry {
    const width = Math.min(DEFAULT_FLOATING_CHAT_SIZE.width, Math.max(FLOAT_MIN_WIDTH, bounds.width - FLOAT_MARGIN * 2));
    const height = Math.min(DEFAULT_FLOATING_CHAT_SIZE.height, Math.max(FLOAT_MIN_HEIGHT, bounds.height - FLOAT_MARGIN * 2));
    return clampGeometry(
        {
            x: bounds.width - width - FLOAT_MARGIN,
            y: bounds.height - height - FLOAT_MARGIN,
            width,
            height,
        },
        bounds,
    );
}

function getFallbackFloatingBounds(): { width: number; height: number } {
    if (typeof window === 'undefined') {
        return { width: 1280, height: 760 };
    }
    return { width: window.innerWidth, height: window.innerHeight };
}

function isPreviousDefaultGeometry(geom: FloatingChatGeometry): boolean {
    return (
        geom.x === PREVIOUS_DEFAULT_FLOATING_CHAT.x &&
        geom.y === PREVIOUS_DEFAULT_FLOATING_CHAT.y &&
        geom.width === PREVIOUS_DEFAULT_FLOATING_CHAT.width &&
        geom.height === PREVIOUS_DEFAULT_FLOATING_CHAT.height
    );
}

function getResizeCursor(handle: FloatingResizeHandle): string {
    if (handle === 'n' || handle === 's') return 'ns-resize';
    if (handle === 'e' || handle === 'w') return 'ew-resize';
    if (handle === 'ne' || handle === 'sw') return 'nesw-resize';
    return 'nwse-resize';
}

function resizeFloatingGeometry(
    handle: FloatingResizeHandle,
    startGeometry: FloatingChatGeometry,
    deltaX: number,
    deltaY: number,
    bounds: { width: number; height: number },
): FloatingChatGeometry {
    const maxWidth = Math.max(FLOAT_MIN_WIDTH, bounds.width - FLOAT_MARGIN * 2);
    const maxHeight = Math.max(FLOAT_MIN_HEIGHT, bounds.height - FLOAT_MARGIN * 2);
    const right = startGeometry.x + startGeometry.width;
    const bottom = startGeometry.y + startGeometry.height;
    let { x, y, width, height } = startGeometry;

    if (handle.includes('e')) {
        width = clampNumber(startGeometry.width + deltaX, FLOAT_MIN_WIDTH, maxWidth);
    }
    if (handle.includes('s')) {
        height = clampNumber(startGeometry.height + deltaY, FLOAT_MIN_HEIGHT, maxHeight);
    }
    if (handle.includes('w')) {
        width = clampNumber(startGeometry.width - deltaX, FLOAT_MIN_WIDTH, maxWidth);
        x = right - width;
    }
    if (handle.includes('n')) {
        height = clampNumber(startGeometry.height - deltaY, FLOAT_MIN_HEIGHT, maxHeight);
        y = bottom - height;
    }

    return clampGeometry({ x, y, width, height }, bounds);
}

/**
 * SAWorkspace — Schedule Assistant workspace shell.
 *
 * Owns the simplified Schedule Assistant canvas: Gantt fills the background,
 * and chat floats above it as a draggable, resizable panel.
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
            raw === 'gantt-full-chat-floating' ? 'gantt-full-chat-floating' : null,
        ) ?? 'gantt-full-chat-floating'
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
    const [initialFloatingChat] = useState<{ geometry: FloatingChatGeometry; shouldPlace: boolean }>(() => {
        const stored = readStored<FloatingChatGeometry>(storageKeys.floatingChat, (raw) => {
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
        });
        if (stored && !isPreviousDefaultGeometry(stored)) {
            return { geometry: stored, shouldPlace: false };
        }
        return { geometry: getDefaultFloatingChat(getFallbackFloatingBounds()), shouldPlace: true };
    });
    const [shouldPlaceFloatingChat, setShouldPlaceFloatingChat] = useState(initialFloatingChat.shouldPlace);
    const [floatingChat, setFloatingChat] = useState<FloatingChatGeometry>(initialFloatingChat.geometry);

    useEffect(() => {
        if (!shouldPlaceFloatingChat || typeof window === 'undefined') return;
        const frameId = window.requestAnimationFrame(() => {
            const rect = workspaceRef.current?.getBoundingClientRect();
            const bounds = rect
                ? { width: rect.width, height: rect.height }
                : getFallbackFloatingBounds();
            setFloatingChat(getDefaultFloatingChat(bounds));
            setShouldPlaceFloatingChat(false);
        });
        return () => window.cancelAnimationFrame(frameId);
    }, [shouldPlaceFloatingChat]);

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

    // -- Effective mode -----------------------------------------------------
    const effectiveMode = useMemo<SAEffectiveMode>(() => 'gantt-full-chat-floating', []);

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
    const resizeStateRef = useRef<{
        handle: FloatingResizeHandle;
        startMouseX: number;
        startMouseY: number;
        startGeometry: FloatingChatGeometry;
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
        document.body.style.setProperty('user-select', 'none');
        document.body.style.setProperty('cursor', 'grabbing');
    };

    const startFloatingResize = (event: React.MouseEvent<HTMLDivElement>, handle: FloatingResizeHandle) => {
        event.preventDefault();
        event.stopPropagation();
        resizeStateRef.current = {
            handle,
            startMouseX: event.clientX,
            startMouseY: event.clientY,
            startGeometry: floatingChat,
        };
        document.body.style.setProperty('user-select', 'none');
        document.body.style.setProperty('cursor', getResizeCursor(handle));
    };

    useEffect(() => {
        const onMove = (event: MouseEvent) => {
            const drag = dragStateRef.current;
            const rect = workspaceRef.current?.getBoundingClientRect();
            const bounds = rect
                ? { width: rect.width, height: rect.height }
                : { width: window.innerWidth, height: window.innerHeight };
            const resize = resizeStateRef.current;
            if (resize) {
                const dx = event.clientX - resize.startMouseX;
                const dy = event.clientY - resize.startMouseY;
                setFloatingChat(resizeFloatingGeometry(resize.handle, resize.startGeometry, dx, dy, bounds));
                return;
            }
            if (!drag) return;
            const dx = event.clientX - drag.startMouseX;
            const dy = event.clientY - drag.startMouseY;
            setFloatingChat((prev) => clampGeometry(
                { ...prev, x: drag.startX + dx, y: drag.startY + dy },
                bounds,
            ));
        };
        const onUp = () => {
            if (!dragStateRef.current && !resizeStateRef.current) return;
            dragStateRef.current = null;
            resizeStateRef.current = null;
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
        <div className={`flex-1 flex flex-col min-h-0 min-w-0 ${sidebarOffsetClass} relative`}>
            {/* Gantt fills the canvas */}
            {ganttPanel?.data && (
                <div className="flex-1 min-h-0 min-w-0 flex flex-col">
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
                        layoutMode="gantt-full-chat-floating"
                    />
                </div>
            )}

            {/* Floating chat panel */}
            <div
                className="absolute min-h-0 bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl flex flex-col overflow-hidden z-40"
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
                    layoutMode="gantt-full-chat-floating"
                    showProjectSelector={shellMode === 'standalone'}
                />
                {renderChatBody('floating')}
                {renderChatFooterInput()}
                {FLOATING_RESIZE_HANDLES.map((handle) => (
                    <div
                        key={handle.handle}
                        className={handle.className}
                        onMouseDown={(event) => startFloatingResize(event, handle.handle)}
                        role="separator"
                        aria-label={handle.label}
                    />
                ))}
                <div className="pointer-events-none absolute bottom-1 right-1 h-3 w-3 border-b border-r border-gray-500/60" />
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
            <div className={`flex-1 flex min-h-0 min-w-0 ${sidebarOffsetClass}`}>
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
