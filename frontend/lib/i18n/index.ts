import { useUser } from '@/lib/contexts/UserContext';

export type SupportedLanguage = 'en' | 'es';

export const translations = {
    en: {
        'welcome': 'Welcome',
        'settings': 'Settings',
        'profile': 'Profile',
        'logout': 'Logout',
        'theme': 'Theme',
        'language': 'Language',
        'notifications': 'Notifications',
        'greeting': 'Hi',
        'newConversation': 'New conversation',
        'previousConversations': 'Previous conversations',
        'sendMessage': 'Send message',
        'typeMessage': 'Type a message...',
        'thinking': 'Thinking...',
        'signOut': 'Sign out',
        'assistant': 'ASSISTANT',
        'dashboard': 'DASHBOARD',
        'actions': 'ACTIONS',
        'actions.send': 'Send',
        'actions.cancel': 'Cancel',
        'actions.confirm': 'Confirm',
        'actions.delete': 'Delete',
        'actions.edit': 'Edit',
        'actions.save': 'Save',
        'agentStates.starting': 'STARTING',
        'agentStates.initializing': 'INITIALIZING',
        'agentStates.processingRequest': 'PROCESSING REQUEST',
        'agentStates.orchestrating': 'ORCHESTRATING',
        'agentStates.analyzingRisk': 'ANALYZING RISK',
        'agentStates.draftingCommunication': 'DRAFTING COMMUNICATION',
        'agentStates.error': 'ERROR',
        'RISK MANAGER': 'RISK MANAGER',
        'SCHEDULE ASSISTANT': 'SCHEDULE ASSISTANT',
    },
    es: {
        'welcome': 'Bienvenido',
        'settings': 'Configuración',
        'profile': 'Perfil',
        'logout': 'Cerrar sesión',
        'theme': 'Tema',
        'language': 'Idioma',
        'notifications': 'Notificaciones',
        'greeting': 'Hola',
        'newConversation': 'Nueva conversación',
        'previousConversations': 'Conversaciones anteriores',
        'sendMessage': 'Enviar mensaje',
        'typeMessage': 'Escribe un mensaje...',
        'thinking': 'Pensando...',
        'signOut': 'Cerrar sesión',
        'assistant': 'ASISTENTE',
        'dashboard': 'PANEL',
        'actions': 'ACCIONES',
        'actions.send': 'Enviar',
        'actions.cancel': 'Cancelar',
        'actions.confirm': 'Confirmar',
        'actions.delete': 'Eliminar',
        'actions.edit': 'Editar',
        'actions.save': 'Guardar',
        'agentStates.starting': 'INICIANDO',
        'agentStates.initializing': 'INICIALIZANDO',
        'agentStates.processingRequest': 'PROCESANDO SOLICITUD',
        'agentStates.orchestrating': 'ORQUESTANDO',
        'agentStates.analyzingRisk': 'ANALIZANDO RIESGO',
        'agentStates.draftingCommunication': 'REDACTANDO COMUNICACIÓN',
        'agentStates.error': 'ERROR',
        'RISK MANAGER': 'GESTOR DE RIESGOS',
        'SCHEDULE ASSISTANT': 'ASISTENTE DE AGENDA',
    }
};

export type TranslationKey =
    | 'greeting'
    | 'newConversation'
    | 'previousConversations'
    | 'typeMessage'
    | 'thinking'
    | 'assistant'
    | 'dashboard'
    | 'actions'
    | 'settings'
    | 'signOut'
    | 'actions.send'
    | 'actions.cancel'
    | 'actions.confirm'
    | 'actions.delete'
    | 'actions.edit'
    | 'actions.save'
    | 'agentStates.starting'
    | 'agentStates.initializing'
    | 'agentStates.processingRequest'
    | 'agentStates.orchestrating'
    | 'agentStates.analyzingRisk'
    | 'agentStates.draftingCommunication'
    | 'agentStates.error'
    | 'RISK MANAGER'
    | 'SCHEDULE ASSISTANT';

export const useTranslation = (language: SupportedLanguage = 'en') => {
    const { user } = useUser();
    const userLanguage = user?.preferences?.language || 'en';
    return translations[userLanguage as keyof typeof translations];
};
