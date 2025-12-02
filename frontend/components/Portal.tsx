import { ReactNode, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * Portal component to render children at document.body level.
 * Prevents z-index stacking issues.
 */
export function Portal({ children }: { children: ReactNode }) {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        return () => setMounted(false);
    }, []);

    return mounted ? createPortal(children, document.body) : null;
}
