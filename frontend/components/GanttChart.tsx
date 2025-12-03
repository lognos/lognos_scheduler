import React from 'react';
import { format, parseISO, differenceInDays, addMonths, startOfMonth } from 'date-fns';
import { Calendar } from 'lucide-react';
import { ScheduleItem } from '@/types';

interface GanttChartProps {
  data: ScheduleItem[];
  loading?: boolean;
}

const GanttChart: React.FC<GanttChartProps> = ({ data, loading }) => {
  if (loading) {
    return (
      <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700">
        <div className="flex items-center gap-2 mb-4">
          <Calendar className="h-5 w-5 text-blue-400" />
          <h3 className="text-xl font-light text-white">Project Schedule</h3>
        </div>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700">
        <div className="flex items-center gap-2 mb-4">
          <Calendar className="h-5 w-5 text-blue-400" />
          <h3 className="text-xl font-light text-white">Project Schedule</h3>
        </div>
        <div className="flex items-center justify-center h-64 text-gray-400">
          No schedule data available
        </div>
      </div>
    );
  }

  // Generate timeline months
  const generateTimeline = React.useMemo(() => {
    if (!data || data.length === 0) return { months: [], totalDays: 0, startDate: new Date() };
    
    try {
      const allStartDates = data.map(item => parseISO(item.start));
      const allEndDates = data.map(item => parseISO(item.finish));
      
      const projectStart = new Date(Math.min(...allStartDates.map(d => d.getTime())));
      const projectEnd = new Date(Math.max(...allEndDates.map(d => d.getTime())));
      
      // Start from the beginning of the start month
      const timelineStart = startOfMonth(projectStart);
      // End at the end of the end month to ensure full month coverage
      const timelineEnd = addMonths(startOfMonth(projectEnd), 1);
      
      const months = [];
      let currentDate = new Date(timelineStart);
      
      while (currentDate < timelineEnd) {
        months.push({
          date: new Date(currentDate),
          label: format(currentDate, 'MMM yyyy'),
          shortLabel: format(currentDate, 'MMM')
        });
        currentDate = addMonths(currentDate, 1);
      }
      
      // Calculate total days from timeline start to timeline end
      const totalDays = differenceInDays(timelineEnd, timelineStart);
      
      return { months, totalDays, startDate: timelineStart };
    } catch (error) {
      console.error('Error generating timeline:', error);
      return { months: [], totalDays: 0, startDate: new Date() };
    }
  }, [data]);

  // Process data for Gantt bars
  const processedData = React.useMemo(() => {
    if (!data || data.length === 0 || generateTimeline.totalDays === 0) return [];
    
    try {
      return data
        .sort((a, b) => new Date(a.finish).getTime() - new Date(b.finish).getTime())
        .map((item, index) => {
          const startDate = parseISO(item.start);
          const finishDate = parseISO(item.finish);
        
        // Calculate position as percentage of total timeline
        const daysFromTimelineStart = differenceInDays(startDate, generateTimeline.startDate);
        // Add 1 to include both start and end dates (finish date is inclusive)
        const duration = differenceInDays(finishDate, startDate) + 1;
        
        const startPercentage = (daysFromTimelineStart / generateTimeline.totalDays) * 100;
        const widthPercentage = (duration / generateTimeline.totalDays) * 100;
        
        return {
          ...item,
          startPercentage: Math.max(0, startPercentage),
          widthPercentage: Math.max(1, widthPercentage),
          duration,
          index
        };
      });
    } catch (error) {
      console.error('Error processing schedule data:', error);
      return [];
    }
  }, [data, generateTimeline]);

  // Colors for different tasks
  const getBarColor = (index: number) => {
    const colors = ['#3B82F6']; /*, '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4'];*/
    return colors[index % colors.length];
  };

  return (
    <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700 print:bg-white print:border print:border-gray-300 print:rounded-none print:page-break-inside-avoid chart-color-preserve">
      <div className="flex items-center justify-between mb-6 print:mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-blue-400 print:text-black" />
          <h3 className="text-xl font-light text-white print:text-black print:font-helvetica">Project L1 schedule</h3>
        </div>
        <div className="text-sm text-gray-400 print:text-black">
          {data.length} schedule item{data.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Timeline Header */}
      <div className="mb-4">
        {/* Year row */}
        <div className="flex">
          <div className="w-80"></div>
          <div className="flex-1 flex text-xs text-gray-500 print:text-black">
            {(() => {
              const yearGroups: { year: string; monthCount: number }[] = [];
              let currentYear = '';
              let monthCount = 0;
              
              generateTimeline.months.forEach((month) => {
                const year = format(month.date, 'yyyy');
                if (year !== currentYear) {
                  if (currentYear) {
                    yearGroups.push({ year: currentYear, monthCount });
                  }
                  currentYear = year;
                  monthCount = 1;
                } else {
                  monthCount++;
                }
              });
              
              if (currentYear) {
                yearGroups.push({ year: currentYear, monthCount });
              }
              
              return yearGroups.map((group, index) => (
                <div 
                  key={index} 
                  className="text-center font-medium"
                  style={{ flex: group.monthCount }}
                >
                  {group.year}
                </div>
              ));
            })()}
          </div>
        </div>
        {/* Month row */}
        <div className="flex border-b border-dark-600 print:border-gray-300 pb-2">
          <div className="w-80 text-xs font-medium text-gray-400 print:text-black">Activity</div>
          <div className="flex-1 flex text-xs text-gray-400 print:text-black">
            {generateTimeline.months.map((month, index) => (
              <div key={index} className="flex-1 text-center border-r border-dark-600 print:border-gray-300 last:border-r-0">
                {month.shortLabel}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Gantt Bars */}
      <div className="space-y-3">
        {processedData.map((item, taskIndex) => (
          <div key={item.s_item_id} className="flex items-center group">
            {/* Task Label */}
            <div className="w-80 pr-4">
              <div className="text-xs font-medium text-white print:text-black truncate">
                {item.s_item}
              </div>
              <div className="text-xs text-gray-500 print:text-black">
                {item.s_item_id}
              </div>
            </div>
            
            {/* Timeline Bar Container */}
            <div className="flex-1 relative h-8 rounded">
              {/* Container for bars only - no grid lines or background */}
              
              {/* Task Bar */}
              <div
                className="absolute top-1 bottom-1 rounded transition-all duration-200 group-hover:opacity-80 flex items-center justify-center text-xs font-medium shadow-lg gantt-bar"
                style={{
                  left: `${item.startPercentage}%`,
                  width: `${item.widthPercentage}%`,
                  backgroundColor: getBarColor(taskIndex),
                  minWidth: '20px',
                  color: 'white' // Default color for screen
                }}
                title={`${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Duration: ${item.total_duration} days`}
              >
                {item.widthPercentage > 8 && (
                  <span 
                    className="truncate px-1 gantt-duration-text"
                    style={{ color: 'inherit' }}
                  >
                    {item.total_duration}d
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default GanttChart;
