export interface Project {
    project_id: string;
    project_name: string;
    company_id?: string | null;
    project_overview?: string | null;
    metadata?: Record<string, any>;
    created_at?: string | null;
}
