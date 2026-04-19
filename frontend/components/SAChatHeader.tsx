import React from 'react';
import { MessageSquare, SquarePen, Pin, PinOff, PanelLeft, PanelRight } from 'lucide-react';
import { ProjectSelector } from './ProjectSelector';
import { useUser } from '@/lib/contexts/UserContext';
import { SAWorkspaceMode, SAWorkspaceLayoutActions } from '@/types/workspace';

interface SAChatHeaderProps {
    onHistoryToggle: () => void;
    onNewConversation: () => void;
    layoutMode?: SAWorkspaceMode;
    layoutActions?: SAWorkspaceLayoutActions;
    showProjectSelector?: boolean;
}

export const SAChatHeader: React.FC<SAChatHeaderProps> = ({
    onHistoryToggle,
    onNewConversation,
    layoutMode,
    layoutActions,
    showProjectSelector = true,
}) => {
    const { t } = useUser();

    const showPinRight = !!layoutActions && layoutMode === 'gantt-full-chat-floating';
    const showUnpinFloat = !!layoutActions && layoutMode !== 'gantt-full-chat-floating';
    const showSwapToB = !!layoutActions && layoutMode === 'chat-main-gantt-side';
    const showSwapToC = !!layoutActions && layoutMode === 'gantt-main-chat-side';

    return (
        <div className="w-full p-6 z-40 flex items-center justify-between pointer-events-none">
            <div className="pointer-events-auto">
                {showProjectSelector && <ProjectSelector isHovered={true} />}
            </div>
            <div className="flex items-center gap-2 pointer-events-auto">
                {showPinRight && (
                    <button
                        onClick={layoutActions!.pinChatRight}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        title="Pin chat to side"
                        aria-label="Pin chat to side"
                    >
                        <Pin size={20} />
                    </button>
                )}
                {showUnpinFloat && (
                    <button
                        onClick={layoutActions!.unpinChatToFloating}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        title="Unpin chat (floating)"
                        aria-label="Unpin chat"
                    >
                        <PinOff size={20} />
                    </button>
                )}
                {showSwapToB && (
                    <button
                        onClick={layoutActions!.swapSides}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        title="Move chat to right"
                        aria-label="Move chat to right"
                    >
                        <PanelRight size={20} />
                    </button>
                )}
                {showSwapToC && (
                    <button
                        onClick={layoutActions!.swapSides}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        title="Move chat to left"
                        aria-label="Move chat to left"
                    >
                        <PanelLeft size={20} />
                    </button>
                )}
                <button
                    onClick={onHistoryToggle}
                    className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                    title={t('previousConversations')}
                >
                    <MessageSquare size={20} />
                </button>
                <button
                    className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                    title={t('newConversation')}
                    onClick={onNewConversation}
                >
                    <SquarePen size={20} />
                </button>
            </div>
        </div>
    );
};
