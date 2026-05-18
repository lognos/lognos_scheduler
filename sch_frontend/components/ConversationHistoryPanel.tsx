import React, { useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Portal } from '@/components/Portal';
import { ConversationSkeleton } from '@/components/ConversationSkeleton';
import { useClickOutside } from '@/hooks/useClickOutside';
import { useConversations, ConversationSummary } from '@/hooks/useConversations';
import { formatRelativeTime } from '@/utils/time';

interface ConversationHistoryPanelProps {
    isOpen: boolean;
    onClose: () => void;
    onSelectConversation: (id: string) => Promise<void>;
    currentConversationId: string | null;
    userEmail: string;
}

export function ConversationHistoryPanel({
    isOpen,
    onClose,
    onSelectConversation,
    currentConversationId,
    userEmail,
}: ConversationHistoryPanelProps) {
    const {
        conversations,
        isLoading,
        error,
        hideConversation,
        fetchConversations
    } = useConversations(userEmail);

    const panelRef = useRef<HTMLDivElement>(null);
    const [selectedIndex, setSelectedIndex] = useState(0);

    // Fetch on mount AND when reopened (respects cache)
    useEffect(() => {
        if (isOpen) {
            fetchConversations();
        }
    }, [isOpen, fetchConversations]);

    // Click outside to close
    useClickOutside(panelRef, onClose);

    // Keyboard navigation
    useEffect(() => {
        if (!isOpen) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            switch (e.key) {
                case 'Escape':
                    onClose();
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    setSelectedIndex(i => Math.min(i + 1, conversations.length - 1));
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    setSelectedIndex(i => Math.max(i - 1, 0));
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (conversations[selectedIndex]) {
                        onSelectConversation(conversations[selectedIndex].conversation_id);
                    }
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isOpen, selectedIndex, conversations, onClose, onSelectConversation]);

    if (!isOpen) return null;

    return (
        <Portal>
            <div
                ref={panelRef}
                className="fixed top-16 right-6 w-96 bg-[#1e2530] border border-gray-700 
                           rounded-xl shadow-xl z-50 max-h-[32rem] overflow-hidden flex flex-col"
                role="dialog"
                aria-modal="true"
                aria-label="Conversation history"
            >
                {/* Header */}


                {/* Content */}
                <div className="flex-1 overflow-y-auto">
                    {isLoading ? (
                        <div className="py-2">
                            {Array.from({ length: 5 }).map((_, i) => (
                                <ConversationSkeleton key={i} />
                            ))}
                        </div>
                    ) : error ? (
                        <div className="p-4 text-red-400 text-sm">
                            Error loading conversations: {error}
                        </div>
                    ) : conversations.length === 0 ? (
                        <div className="p-8 text-center text-gray-400">
                            No conversations yet
                        </div>
                    ) : (
                        <div className="py-2">
                            {conversations.map((conv, index) => (
                                <ConversationItem
                                    key={conv.conversation_id}
                                    conversation={conv}
                                    isActive={conv.conversation_id === currentConversationId}
                                    isSelected={index === selectedIndex}
                                    onClick={() => onSelectConversation(conv.conversation_id)}
                                    onHide={() => hideConversation(conv.conversation_id)}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </Portal>
    );
}

// Memoized list item for performance
const ConversationItem = React.memo(function ConversationItem({
    conversation,
    isActive,
    isSelected,
    onClick,
    onHide,
}: {
    conversation: ConversationSummary;
    isActive: boolean;
    isSelected: boolean;
    onClick: () => void;
    onHide: () => void;
}) {
    return (
        <div
            className={`
                px-4 py-3 flex items-start gap-3 cursor-pointer
                hover:bg-white/5 transition-colors
                ${isActive ? 'bg-blue-500/10 border-l-2 border-l-blue-500' : ''}
                ${isSelected ? 'bg-white/5' : ''}
            `}
            onClick={onClick}
            role="button"
            tabIndex={0}
            aria-label={`Load conversation: ${conversation.title}`}
        >
            <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">
                    {conversation.title}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                    {formatRelativeTime(conversation.last_message_at)} · {conversation.message_count} messages
                </p>
            </div>
            <button
                onClick={(e) => {
                    e.stopPropagation();
                    onHide();
                }}
                className="p-1 text-gray-400 hover:text-red-400 transition-colors flex-shrink-0"
                aria-label="Hide conversation"
            >
                <Trash2 size={16} />
            </button>
        </div>
    );
});
