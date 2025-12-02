import React from 'react';
import { MessageSquare, SquarePen } from 'lucide-react';
import { ProjectSelector } from './ProjectSelector';
import { useUser } from '@/lib/contexts/UserContext';

interface ChatHeaderProps {
    onHistoryToggle: () => void;
    onNewConversation: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
    onHistoryToggle,
    onNewConversation,
}) => {
    const { t } = useUser();

    return (
        <div className="w-full p-6 z-40 flex items-center justify-between pointer-events-none">
            {/* Left Side: Project Selector */}
            <div className="pointer-events-auto">
                <ProjectSelector isHovered={true} />
            </div>

            {/* Right Side: Actions */}
            <div className="flex items-center gap-2 pointer-events-auto">
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
