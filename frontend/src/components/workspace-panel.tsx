"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Calendar as CalendarIcon, 
  Mail, 
  MessageSquare, 
  CreditCard, 
  CheckSquare, 
  BarChart2, 
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  Bell
} from "lucide-react";

type AppName = "calendar" | "gmail" | "slack" | "payments" | "tasks" | "insights" | null;

const APPS = [
  { id: "calendar", name: "Calendar", icon: CalendarIcon, gradient: "from-blue-500 to-cyan-400", shadow: "shadow-cyan-500/20" },
  { id: "gmail", name: "Mail", icon: Mail, gradient: "from-rose-500 to-orange-400", shadow: "shadow-orange-500/20" },
  { id: "slack", name: "Slack", icon: MessageSquare, gradient: "from-fuchsia-500 to-purple-600", shadow: "shadow-purple-500/20" },
  { id: "payments", name: "Payments", icon: CreditCard, gradient: "from-emerald-400 to-teal-500", shadow: "shadow-teal-500/20" },
  { id: "tasks", name: "Tasks", icon: CheckSquare, gradient: "from-amber-400 to-orange-500", shadow: "shadow-orange-500/20" },
  { id: "insights", name: "Insights", icon: BarChart2, gradient: "from-indigo-400 to-blue-600", shadow: "shadow-indigo-500/20" },
];

function FullCalendarMock() {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  // Generate 35 days for a 5-week calendar view grid
  const dates = Array.from({ length: 35 }, (_, i) => i - 2); 

  return (
    <div className="flex flex-col h-full bg-[#0a0a0c]">
      {/* Premium Calendar Header */}
      <div className="flex items-center justify-between p-5 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-5">
          <h2 className="text-2xl font-bold text-zinc-100 tracking-tight">June 2026</h2>
          <div className="flex items-center gap-1 bg-zinc-900/50 rounded-lg p-1 border border-white/5 backdrop-blur-md">
            <button className="p-1.5 hover:bg-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors"><ChevronLeft className="w-4 h-4" /></button>
            <button className="px-3 py-1 text-xs font-semibold text-zinc-300 hover:text-zinc-100 transition-colors">Today</button>
            <button className="p-1.5 hover:bg-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors"><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="bg-zinc-900/50 rounded-lg p-1 border border-white/5 flex text-xs font-semibold backdrop-blur-md">
            <button className="px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-100 shadow-sm">Month</button>
            <button className="px-3 py-1.5 rounded-md text-zinc-400 hover:text-zinc-200 transition-colors">Week</button>
            <button className="px-3 py-1.5 rounded-md text-zinc-400 hover:text-zinc-200 transition-colors">Day</button>
          </div>
          <button className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-400 hover:to-indigo-400 text-white rounded-lg text-sm font-semibold transition-all shadow-lg shadow-blue-500/25 border border-blue-400/20">
            <Plus className="w-4 h-4" /> Add Event
          </button>
        </div>
      </div>

      {/* Calendar Grid Body */}
      <div className="flex-1 overflow-auto p-6 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900/40 via-[#0a0a0c] to-[#0a0a0c]">
        <div className="h-full rounded-2xl border border-white/10 bg-[#111113]/80 backdrop-blur-xl shadow-2xl flex flex-col overflow-hidden ring-1 ring-white/5">
          <div className="grid grid-cols-7 border-b border-white/5 bg-black/20">
            {days.map(d => (
              <div key={d} className="p-3 text-center text-[11px] font-bold text-zinc-500 uppercase tracking-widest">
                {d}
              </div>
            ))}
          </div>
          
          <div className="flex-1 grid grid-cols-7 grid-rows-5 gap-px bg-white/5">
            {dates.map((date, i) => {
              const isCurrentMonth = date > 0 && date <= 30;
              const isToday = date === 13;
              const displayDate = date > 0 ? (date > 30 ? date - 30 : date) : 31 + date;
              
              return (
                <div key={i} className={`bg-[#111113] p-2 hover:bg-[#161618] transition-colors group relative ${!isCurrentMonth ? 'opacity-40' : ''}`}>
                  <div className={`text-sm font-bold w-7 h-7 flex items-center justify-center rounded-full mb-1.5 ${isToday ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30' : 'text-zinc-400 group-hover:text-zinc-200'}`}>
                    {displayDate}
                  </div>
                  
                  {/* Detailed Mock Events */}
                  <div className="space-y-1.5">
                    {date === 4 && (
                      <div className="text-[10px] font-medium truncate px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors cursor-pointer">
                        Product Launch
                      </div>
                    )}
                    {date === 13 && (
                      <>
                        <div className="text-[10px] font-medium truncate px-2 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors cursor-pointer flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span> 10am Design
                        </div>
                        <div className="text-[10px] font-medium truncate px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors cursor-pointer flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> 2pm 1on1
                        </div>
                      </>
                    )}
                    {date === 18 && (
                      <div className="text-[10px] font-medium truncate px-2 py-1 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20 hover:bg-orange-500/20 transition-colors cursor-pointer flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-orange-500"></span> All Hands
                      </div>
                    )}
                    {date === 22 && (
                      <div className="text-[10px] font-medium truncate px-2 py-1 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 transition-colors cursor-pointer flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span> Offsite Planning
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function GenericMockApp({ app }: { app: typeof APPS[0] }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-[#0a0a0c] p-8">
      <div className="text-center space-y-6">
        <div className={`w-24 h-24 mx-auto rounded-3xl bg-gradient-to-br ${app.gradient} p-0.5 shadow-2xl ${app.shadow} animate-pulse`}>
          <div className="w-full h-full bg-[#111113] rounded-[22px] flex items-center justify-center relative overflow-hidden">
             <div className={`absolute inset-0 bg-gradient-to-br ${app.gradient} opacity-20`}></div>
            <app.icon className="w-10 h-10 text-white relative z-10" />
          </div>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-zinc-100 mb-2">{app.name}</h2>
          <p className="text-sm text-zinc-500 max-w-sm mx-auto leading-relaxed">
            This module is currently in mockup mode. More premium UI integrations will be connected soon.
          </p>
        </div>
        <button className="px-6 py-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-sm font-semibold transition-colors">
          Configure Agent Access
        </button>
      </div>
    </div>
  );
}

export function WorkspacePanel() {
  const [activeApp, setActiveApp] = useState<AppName>(null);

  const renderAppContent = () => {
    switch (activeApp) {
      case "calendar":
        return <FullCalendarMock />;
      default:
        const app = APPS.find(a => a.id === activeApp);
        return app ? <GenericMockApp app={app} /> : null;
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0a0c] text-zinc-100 overflow-hidden relative font-sans">
      <AnimatePresence mode="wait">
        {!activeApp ? (
          <motion.div
            key="home"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="flex-1 p-8 flex flex-col relative"
          >
            {/* Ambient Background Gradient */}
            <div className="absolute top-0 left-0 w-full h-96 bg-indigo-500/10 blur-[120px] rounded-full pointer-events-none -translate-y-1/2"></div>
            
            <div className="flex justify-between items-start mb-12 relative z-10">
              <div>
                <h1 className="mb-2 font-serif text-3xl leading-none tracking-tight text-white sm:text-4xl">Workspace</h1>
                <p className="text-sm text-zinc-400 font-medium">Your agent is monitoring 6 integrations</p>
              </div>
              <div className="flex gap-3">
                <button className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors shadow-sm">
                  <Search className="w-4 h-4 text-zinc-300" />
                </button>
                <button className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors relative shadow-sm">
                  <Bell className="w-4 h-4 text-zinc-300" />
                  <span className="absolute top-2 right-2.5 w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-y-10 gap-x-6 relative z-10">
              {APPS.map((app) => (
                <button
                  key={app.id}
                  onClick={() => setActiveApp(app.id as AppName)}
                  className="flex flex-col items-center gap-4 group outline-none"
                >
                  <div className={`w-[72px] h-[72px] rounded-3xl bg-gradient-to-br ${app.gradient} p-0.5 shadow-xl ${app.shadow} group-hover:scale-[1.08] transition-all duration-300 ease-out cursor-pointer`}>
                    <div className="w-full h-full bg-[#111113]/90 backdrop-blur-xl rounded-[22px] flex items-center justify-center relative overflow-hidden">
                      <div className={`absolute inset-0 bg-gradient-to-br ${app.gradient} opacity-0 group-hover:opacity-20 transition-opacity duration-300`}></div>
                      <app.icon className="w-8 h-8 text-white relative z-10 drop-shadow-md" />
                    </div>
                  </div>
                  <span className="text-[13px] font-semibold text-zinc-400 group-hover:text-zinc-100 transition-colors tracking-wide">
                    {app.name}
                  </span>
                </button>
              ))}
            </div>
            
            {/* Activity Feed Widget */}
            <div className="mt-auto pt-8 relative z-10">
              <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-5 backdrop-blur-md shadow-lg">
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Recent Agent Activity</h3>
                <div className="space-y-4">
                  <div className="flex items-center gap-4 p-3 rounded-xl hover:bg-white/[0.02] transition-colors cursor-pointer border border-transparent hover:border-white/5">
                    <div className="w-10 h-10 rounded-full bg-blue-500/10 text-blue-400 flex items-center justify-center border border-blue-500/20 shrink-0 shadow-sm">
                      <CalendarIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-zinc-200">Rescheduled Design Review</p>
                      <p className="text-xs text-zinc-500 mt-0.5">Moved to 10:00 AM based on your Slack preference.</p>
                    </div>
                    <span className="ml-auto text-xs font-medium text-zinc-600">2m ago</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="app"
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="flex-1 flex flex-col bg-[#0a0a0c] z-20"
          >
            {/* Unified App Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/5 bg-black/20 backdrop-blur-xl relative z-30">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setActiveApp(null)}
                  className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-zinc-100 transition-colors border border-white/5 shadow-sm"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="flex items-center gap-2.5">
                  <div className={`w-7 h-7 rounded-lg bg-gradient-to-br ${APPS.find(a => a.id === activeApp)?.gradient} p-px shadow-sm`}>
                    <div className="w-full h-full bg-[#111113] rounded-[7px] flex items-center justify-center">
                      {(() => {
                        const Icon = APPS.find(a => a.id === activeApp)?.icon;
                        return Icon ? <Icon className="w-4 h-4 text-white" /> : null;
                      })()}
                    </div>
                  </div>
                  <h2 className="text-[15px] font-bold text-white tracking-wide">
                    {APPS.find(a => a.id === activeApp)?.name}
                  </h2>
                </div>
              </div>
            </div>
            
            {/* App Content Frame */}
            <div className="flex-1 overflow-hidden relative">
              {renderAppContent()}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
