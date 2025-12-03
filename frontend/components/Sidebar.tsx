import React, { useState } from 'react';
import { clsx } from 'clsx';
import { MessageSquare, LayoutDashboard, Zap, Settings, LogOut, User } from 'lucide-react';
import LognosLogo from './LognosLogo';
import { useAuth } from './providers/AuthProvider';
import { useUser } from '@/lib/contexts/UserContext';


export const Sidebar: React.FC = () => {
    const [isHovered, setIsHovered] = useState(false);
    const { signOut } = useAuth();
    const { user, t } = useUser();

    const handleSignOut = async () => {
        try {
            await signOut();
        } catch (error) {
            console.error('Error signing out:', error);
        }
    };

    const TextIcon = ({ text }: { text: string }) => (
        <span className="text-sm font-bold tracking-tighter w-6 h-6 flex items-center justify-center">
            {text}
        </span>
    );

    return (
        <div
            className={clsx(
                'fixed left-0 top-0 h-full bg-black/20 backdrop-blur-sm transition-all duration-300 ease-in-out z-50',
                isHovered ? 'w-64' : 'w-16'
            )}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            <div className="flex flex-col h-full">
                {/* Logo Section */}
                <div className="p-4 relative h-12">
                    <div className="absolute left-4 top-1/2 transform -translate-y-1/2">
                        <LognosLogo
                            isExpanded={isHovered}
                            size={24}
                            circleColor="#3B82F6"
                        />
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 pt-20">
                    <ul className="space-y-2">
                        <li>
                            <NavItem
                                icon={<TextIcon text="RM" />}
                                label={t('RISK MANAGER')}

                                isHovered={isHovered}
                            />
                        </li>
                        <li>
                            <NavItem
                                icon={<TextIcon text="SA" />}
                                label={t('SCHEDULE ASSISTANT')}
                                isActive
                                isHovered={isHovered}
                            />
                        </li>
                        <li>
                            <NavItem
                                icon={<LayoutDashboard size={20} />}
                                label={t('dashboard')}
                                isHovered={isHovered}
                            />
                        </li>
                    </ul>
                </nav>

                {/* Bottom Section */}
                <div className="pb-2">
                    <NavItem icon={<Zap size={20} />} label={t('actions')} isHovered={isHovered} />
                    <NavItem icon={<Settings size={20} />} label={t('settings')} isHovered={isHovered} />
                </div>

                {/* User Info and Sign Out */}
                <div className="pt-2 pb-2">
                    {/* User Info */}
                    <div className="flex items-center px-4 py-2 text-gray-400 group relative">
                        <User size={20} className="flex-shrink-0" />
                        {isHovered && (
                            <div className="ml-3 flex-1 min-w-0">
                                <div className="text-sm font-medium text-white truncate">
                                    {user?.display_name || 'User'}
                                </div>
                                <div className="text-xs text-gray-500 truncate">
                                    {user?.roles?.[0] || 'Role'}
                                </div>
                            </div>
                        )}
                        {!isHovered && (
                            <div className="absolute left-full ml-2 px-2 py-1 bg-dark-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                                {user?.display_name || 'User'}
                            </div>
                        )}
                    </div>

                    {/* Sign Out Button */}
                    <button
                        onClick={handleSignOut}
                        className="w-full flex items-center px-4 py-3 text-left transition-all duration-200 group relative text-gray-400 hover:text-red-400 hover:bg-dark-800/50"
                    >
                        <LogOut
                            size={20}
                            className="flex-shrink-0 transition-colors duration-200 group-hover:text-red-400"
                        />
                        {isHovered && (
                            <span className="ml-3 text-sm font-light transition-all duration-200 animate-fade-in">
                                {t('signOut')}
                            </span>
                        )}

                        {!isHovered && (
                            <div className="absolute left-full ml-2 px-2 py-1 bg-dark-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                                {t('signOut')}
                            </div>
                        )}
                    </button>
                </div>

                {/* Footer */}
                <div className={`p-4 ${!isHovered && 'px-0'}`}>
                    <div
                        className={`text-xs text-gray-500 text-center ${isHovered ? 'animate-fade-in' : 'text-[10px] tracking-tight px-1'
                            }`}
                    >
                        {isHovered ? 'Lognos v0.93' : 'v0.93'}
                    </div>
                </div>
            </div>
        </div>
    );
};

interface NavItemProps {
    icon: React.ReactNode;
    label: string;
    isActive?: boolean;
    isHovered: boolean;
}

const NavItem: React.FC<NavItemProps> = ({ icon, label, isActive, isHovered }) => {
    return (
        <button
            className={clsx(
                'w-full flex items-center px-4 py-3 text-left transition-all duration-200 group relative',
                isActive
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-gray-400 hover:text-white hover:bg-dark-800/50'
            )}
        >
            <div className={clsx('flex-shrink-0 transition-colors duration-200', isActive ? 'text-blue-400' : 'text-gray-400 group-hover:text-white')}>
                {icon}
            </div>
            {isHovered && (
                <span className="ml-3 text-sm font-light transition-all duration-200 animate-fade-in">
                    {label}
                </span>
            )}

            {/* Tooltip for collapsed state */}
            {!isHovered && (
                <div className="absolute left-full ml-2 px-2 py-1 bg-dark-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                    {label}
                </div>
            )}
        </button>
    );
};
