import React, { useEffect, useRef } from 'react';
import { MessageSquare, SquarePen } from 'lucide-react';
import { Message, AgentState } from '@/hooks/useAGUIStream';
import { MessageBubble } from './MessageBubble';
import { ThinkingIndicator } from './ThinkingIndicator';
import { InputArea } from './InputArea';
import { Sidebar } from './Sidebar';
import { ChatHeader } from './ChatHeader';
import { ReviewBadge, ReviewItem } from './ReviewBadge';
import { GanttPanel } from './GanttPanel';
import { useUser } from '@/lib/contexts/UserContext';
import { GanttPanelState } from '@/types/schedule';

// Mock data for review items - TODO: Replace with usePendingActions hook
const mockReviewItems: ReviewItem[] = [
    { id: '1', label: 'Strike risk mitigation validation', color: 'yellow' },
    { id: '2', label: '200T crane confirmation', color: 'red' },
];

interface ChatLayoutProps {
    messages: Message[];
    agentState: AgentState | null;
    isLoading: boolean;
    onSendMessage: (content: string) => void;
    onNewConversation: () => void;
    onHistoryToggle: () => void;
    ganttPanel?: GanttPanelState;
    onHideGanttPanel?: () => void;
}


export const ChatLayout: React.FC<ChatLayoutProps> = ({
    messages,
    agentState,
    isLoading,
    onSendMessage,
    onNewConversation,
    onHistoryToggle,
    ganttPanel,
    onHideGanttPanel,
}) => {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const { user, t } = useUser();
    
    // Determine if Gantt panel is visible
    const isGanttVisible = ganttPanel?.isVisible && ganttPanel?.data;

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, agentState]);

    return (
        <div className="relative flex h-screen bg-[#0d1117] text-white/90 font-light overflow-hidden">
            <Sidebar />

            {/* Main content area - shrinks when Gantt panel is open */}
            <div className={`flex-1 flex flex-col pl-16 transition-all duration-300 relative ${isGanttVisible ? 'mr-[940px]' : ''}`}>
                {/* Header Actions */}
                {/* Header Actions */}
                <ChatHeader
                    onHistoryToggle={onHistoryToggle}
                    onNewConversation={onNewConversation}
                />

                {/* Messages Area */}
                <main className="flex-1 overflow-y-auto p-4 sm:p-6 scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent">
                    <div className="max-w-5xl mx-auto flex flex-col space-y-8 pb-4 pt-8 min-h-full">
                        {messages.length === 0 ? (
                            <div className="flex flex-col items-center justify-center flex-1 h-[70vh] text-center space-y-8">
                                <div className="space-y-4">
                                    <h2 className="text-2xl font-light text-white tracking-tight">

                                    </h2>
                                    <p className="text-4xl text-gray-300 font-light">
                                        {t('greeting')}, {user?.first_name || 'User'}.
                                    </p>
                                </div>
                                <div className="w-full max-w-3xl">
                                    <InputArea onSend={onSendMessage} disabled={isLoading} />
                                </div>
                                {/* <p className="text-1.5xl text-gray-300 font-light">
                                    You have for review{' '}
                                    {mockReviewItems.map((item, index) => (
                                        <span key={item.id}>
                                            <ReviewBadge
                                                item={item}
                                                onClick={(i) => console.log('Clicked review item:', i)}
                                            />
                                            {index < mockReviewItems.length - 1 && ' and '}
                                        </span>
                                    ))}
                                </p> */}
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

                {/* Input Area */}
                {messages.length > 0 && (
                    <footer className="flex-none bg-[#0d1117] pb-8 pt-4 px-4">
                        <InputArea onSend={onSendMessage} disabled={isLoading} />
                    </footer>
                )}
            </div>

            {/* Gantt Panel - Floating side panel */}
            {isGanttVisible && ganttPanel?.data && onHideGanttPanel && (
                <GanttPanel data={ganttPanel.data} onClose={onHideGanttPanel} />
            )}
        </div>
    );
};