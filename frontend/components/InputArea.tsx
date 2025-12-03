import React, { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';
import { useUser } from '@/lib/contexts/UserContext';

interface InputAreaProps {
    onSend: (message: string) => void;
    disabled?: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ onSend, disabled }) => {
    const [input, setInput] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const { t } = useUser();

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!input.trim() || disabled) return;
        onSend(input);
        setInput('');
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
        }
    }, [input]);

    return (
        <div className="w-full max-w-4xl mx-auto">
            <div className="relative flex items-end bg-dark-800 border border-transparent rounded-xl shadow-lg focus-within:border-blue-500 transition-all duration-200">
                <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={t('typeMessage')}
                    disabled={disabled}
                    rows={1}
                    className="w-full py-3 pl-4 pr-12 bg-transparent border-none resize-none focus:ring-0 focus:outline-none max-h-48 overflow-y-auto text-base text-white placeholder-gray-400 font-light leading-relaxed"
                />
                <button
                    onClick={() => handleSubmit()}
                    disabled={!input.trim() || disabled}
                    className="absolute right-3 bottom-2 p-2 text-blue-500 hover:text-blue-400 disabled:text-gray-500 transition-colors rounded-lg hover:bg-blue-500/20"
                >
                    <Send size={16} />
                </button>
            </div>
            {/* <div className="text-center mt-3 text-xs text-gray-500 font-light tracking-wide">
                AI can make mistakes. Please review generated information.
            </div> */}
        </div>
    );
};