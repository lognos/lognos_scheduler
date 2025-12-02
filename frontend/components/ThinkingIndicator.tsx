import React from 'react';
import { motion } from 'framer-motion';
import { AgentState } from '@/hooks/useAGUIStream';
import { useUser } from '@/lib/contexts/UserContext';

interface ThinkingIndicatorProps {
    state: AgentState;
}

export const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = ({ state }) => {
    const { t } = useUser();

    const getNodeLabel = (node: string) => {
        switch (node) {
            case 'Starting': return t('agentStates.starting');
            case 'Initializing': return t('agentStates.initializing');
            case 'HandleUserTurn': return t('agentStates.processingRequest');
            case 'Orchestrator': return t('agentStates.orchestrating');
            case 'RiskAgent': return t('agentStates.analyzingRisk');
            case 'CommunicationsAgent': return t('agentStates.draftingCommunication');
            case 'Error': return t('agentStates.error');
            default: return node.toUpperCase();
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="flex items-center  space-x-3 p-4 w-full max-w-4xl mx-auto"
        >
            <div className="flex space-x-1">
                <motion.div
                    className="w-1.5 h-1.5 bg-gray-500 rounded-full"
                    animate={{ scale: [1, 1.2, 1], opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0 }}
                />
                <motion.div
                    className="w-1.5 h-1.5 bg-gray-500 rounded-full"
                    animate={{ scale: [1, 1.2, 1], opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.2 }}
                />
                <motion.div
                    className="w-1.5 h-1.5 bg-gray-500 rounded-full"
                    animate={{ scale: [1, 1.2, 1], opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.4 }}
                />
            </div>
            <div className="text-sm font-light text-gray-500 animate-pulse flex flex-col">
                {state.reasoning && (
                    <div className="text-xs text-gray-400 mb-1 italic max-w-2xl">
                        {state.reasoning}
                    </div>
                )}
                <div>
                    <span className="uppercase tracking-widest mr-2">
                        {getNodeLabel(state.node)}
                    </span>
                    {state.intent && <span className="text-gray-600 border-l border-gray-700 pl-2">{state.intent}</span>}
                </div>
            </div>
        </motion.div>
    );
};
