"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Project } from '@/types/project';
import { useAuth } from '@/components/providers/AuthProvider';

interface ProjectContextType {
    projects: Project[];
    currentProject: Project | null;
    isLoading: boolean;
    error: string | null;
    selectProject: (projectId: string) => void;
    refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

const PROJECT_STORAGE_KEY = 'lognos_active_project';

export function ProjectProvider({ children }: { children: ReactNode }) {
    const { session, loading: authLoading } = useAuth();
    const [projects, setProjects] = useState<Project[]>([]);
    const [currentProject, setCurrentProject] = useState<Project | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchProjects = async () => {
        if (!session?.access_token) return;

        try {
            setIsLoading(true);
            console.log('Fetching projects with token:', session.access_token.slice(0, 10) + '...');
            // Bypass proxy to debug auth header issue
            const response = await fetch('http://localhost:8500/api/v1/projects/', {
                headers: {
                    'Authorization': `Bearer ${session.access_token}`
                }
            });

            if (!response.ok) {
                throw new Error('Failed to fetch projects');
            }

            const data: Project[] = await response.json();
            setProjects(data);

            // Handle project selection logic
            if (data.length > 0) {
                const savedProjectId = localStorage.getItem(PROJECT_STORAGE_KEY);
                const savedProject = data.find(p => p.project_id === savedProjectId);

                if (savedProject) {
                    setCurrentProject(savedProject);
                } else {
                    // Default to first project if no saved project or saved project not found
                    setCurrentProject(data[0]);
                    localStorage.setItem(PROJECT_STORAGE_KEY, data[0].project_id);
                }
            } else {
                setCurrentProject(null);
            }

        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch projects');
            console.error('Error fetching projects:', err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (!authLoading && session) {
            fetchProjects();
        } else if (!authLoading && !session) {
            setProjects([]);
            setCurrentProject(null);
            setIsLoading(false);
        }
    }, [session, authLoading]);

    const selectProject = (projectId: string) => {
        const project = projects.find(p => p.project_id === projectId);
        if (project) {
            setCurrentProject(project);
            localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
        }
    };

    return (
        <ProjectContext.Provider value={{ 
            projects, 
            currentProject, 
            isLoading, 
            error, 
            selectProject, 
            refreshProjects: fetchProjects 
        }}>
            {children}
        </ProjectContext.Provider>
    );
}

export function useProject() {
    const context = useContext(ProjectContext);
    if (context === undefined) {
        throw new Error('useProject must be used within a ProjectProvider');
    }
    return context;
}
