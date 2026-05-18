import React, { useState, useRef, useEffect } from 'react';
import { clsx } from 'clsx';
import { Briefcase, ChevronDown, Check } from 'lucide-react';
import { useProject } from '@/lib/contexts/ProjectContext';

interface ProjectSelectorProps {
    isHovered?: boolean;
    className?: string;
}

export const ProjectSelector: React.FC<ProjectSelectorProps> = ({ isHovered = true, className }) => {
    const { projects, currentProject, selectProject, isLoading } = useProject();
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    if (isLoading) {
        return (
            <div className="px-4 py-3 animate-pulse">
                <div className="h-5 bg-gray-700 rounded w-full"></div>
            </div>
        );
    }

    if (!projects || projects.length === 0) {
        return null;
    }

    return (
        <div className={clsx("relative px-2", className)} ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={clsx(
                    'flex items-center gap-2 text-lg font-light transition-colors duration-200 group',
                    'text-[#3B82F6] hover:text-blue-400'
                )}
            >
                <span className="truncate max-w-[200px]">
                    {currentProject?.project_name || 'Select Project'}
                </span>
                <ChevronDown size={16} className={clsx("transition-transform duration-200", isOpen && "transform rotate-180")} />
            </button>

            {/* Dropdown Menu */}
            {isOpen && (
                <div className="absolute left-0 mt-2 w-72 bg-[#1e2530] border border-gray-700 rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="py-2 max-h-[60vh] overflow-y-auto">
                        {projects.map((project) => (
                            <button
                                key={project.project_id}
                                onClick={() => {
                                    selectProject(project.project_id);
                                    setIsOpen(false);
                                }}
                                className={clsx(
                                    "w-full flex items-center px-4 py-3 text-sm text-left transition-colors",
                                    currentProject?.project_id === project.project_id
                                        ? "bg-blue-500/10 border-l-2 border-l-blue-500 text-white"
                                        : "text-gray-300 hover:bg-white/5 border-l-2 border-l-transparent"
                                )}
                            >
                                <span className="flex-1 truncate font-light">{project.project_name}</span>
                                {currentProject?.project_id === project.project_id && (
                                    <Check size={16} className="ml-2 flex-shrink-0 text-blue-500" />
                                )}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
