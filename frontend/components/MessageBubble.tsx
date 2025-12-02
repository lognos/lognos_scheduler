import React from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { clsx } from 'clsx';
import { motion, Variants } from 'framer-motion';
import { Message } from '@/hooks/useAGUIStream';

interface MessageBubbleProps {
    message: Message;
}

// Animation variants for block elements
const blockAnimation: Variants = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.8 } }
};

// Custom components for ReactMarkdown to animate blocks as they mount
const MarkdownComponents: Components = {
    p: ({ node, children, className, ...props }) => (
        <motion.p
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("mb-4 last:mb-0", className)}
        >
            {children}
        </motion.p>
    ),
    li: ({ node, children, className, ...props }) => (
        <motion.li
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("ml-4", className)}
        >
            {children}
        </motion.li>
    ),
    h1: ({ node, children, className, id, ...props }) => (
        <motion.h1
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("text-2xl font-semibold mb-4 mt-6", className)}
            id={id}
        >
            {children}
        </motion.h1>
    ),
    h2: ({ node, children, className, id, ...props }) => (
        <motion.h2
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("text-xl font-semibold mb-3 mt-5", className)}
            id={id}
        >
            {children}
        </motion.h2>
    ),
    h3: ({ node, children, className, id, ...props }) => (
        <motion.h3
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("text-lg font-medium mb-2 mt-4", className)}
            id={id}
        >
            {children}
        </motion.h3>
    ),
    blockquote: ({ node, children, className, ...props }) => (
        <motion.blockquote
            variants={blockAnimation}
            initial="hidden"
            animate="visible"
            className={clsx("border-l-4 border-gray-500 pl-4 italic my-4", className)}
        >
            {children}
        </motion.blockquote>
    ),
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
    const isUser = message.role === 'user';

    return (
        <div
            className={clsx(
                'text-base md:text-lg leading-relaxed transition-all duration-200',
                isUser
                    ? 'max-w-4xl rounded-xl px-4 py-3 bg-dark-800 backdrop-blur-sm shadow-lg text-gray-100 self-end'
                    : 'w-full max-w-4xl mx-auto text-gray-100 self-center px-4 py-2'
            )}
        >
            {isUser ? (
                <div className="whitespace-pre-wrap font-light text-gray-100" style={{ fontFamily: 'Helvetica Neue Light, Helvetica Neue, Helvetica, Arial, sans-serif' }}>
                    {message.content}
                </div>
            ) : (
                <div
                    className="prose prose-invert prose-lg max-w-none font-light prose-p:leading-relaxed prose-headings:font-medium prose-a:text-blue-400 hover:prose-a:text-blue-300"
                    style={{ fontFamily: 'Helvetica Neue Light, Helvetica Neue, Helvetica, Arial, sans-serif' }}
                >
                    <ReactMarkdown components={MarkdownComponents} remarkPlugins={[remarkGfm]}>
                        {message.content}
                    </ReactMarkdown>
                </div>
            )}
        </div>
    );
};