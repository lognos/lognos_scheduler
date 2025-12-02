import React from 'react';

interface LognosLogoProps {
  isExpanded: boolean;
  size?: number;
  color?: string;
  circleColor?: string;
  textColor?: string;
}

// Logo component that shows a circle and conditionally shows "lognos" text
const LognosLogo: React.FC<LognosLogoProps> = ({
  isExpanded = false,
  size = 24,
  circleColor = '#3B82F6', // blue-500
  textColor = '#9CA3AF', // gray-400
}) => {
  return (
    <div className="flex items-center">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Circle icon */}
        <circle
          cx="12"
          cy="12"
          r="10"
          stroke={circleColor}
          fill="none"
          strokeWidth="3"
          className="transition-all duration-300"
        />
      </svg>
      
      {/* Text that appears when expanded */}
      {isExpanded && (
        <span 
          className="ml-3 animate-fade-in"
          style={{ 
            fontFamily: "'Helvetica Neue Light', 'Helvetica Neue', Helvetica, Arial, sans-serif",
            fontWeight: 300,
            fontSize: '30px',
            color: textColor,
          }}
        >
          lognos
        </span>
      )}
    </div>
  );
};

export default LognosLogo;
