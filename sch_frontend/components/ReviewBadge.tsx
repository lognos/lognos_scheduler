import React from 'react';

export interface ReviewItem {
    id: string;
    label: string;
    color: 'yellow' | 'red' | 'blue' | 'green';
}

interface ReviewBadgeProps {
    item: ReviewItem;
    onClick?: (item: ReviewItem) => void;
}

const colorStyles = {
    yellow: 'bg-yellow-500/0 text-yellow-400 border-yellow-500/40 hover:bg-yellow-500/10',
    red: 'bg-red-500/0 text-red-400 border-red-500/40 hover:bg-red-500/10',
    blue: 'bg-blue-500/20 text-blue-400 border-blue-500/40 hover:bg-blue-500/30',
    green: 'bg-green-500/20 text-green-400 border-green-500/40 hover:bg-green-500/30',
};

export const ReviewBadge: React.FC<ReviewBadgeProps> = ({ item, onClick }) => {
    return (
        <button
            onClick={() => onClick?.(item)}
            className={`inline-flex items-center px-3 py-1 text-sm font-medium rounded-full border transition-colors cursor-pointer ${colorStyles[item.color]}`}
        >
            {item.label}
        </button>
    );
};
