"use client";

import { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";

export type VisionElement = {
  id: string;
  label: string;
  x: number;
  y: number;
};

// The raw screenshot from the backend is always 1324x968
const NATIVE_WIDTH = 1324;
const NATIVE_HEIGHT = 968;

export function parseVisionElements(analysis: string): VisionElement[] {
  if (!analysis) return [];
  
  const elements: VisionElement[] = [];
  // Match format: Label @ (x, y) or "Label" @ (x, y)
  // Example: Login Button @ (450, 320)
  const regex = /([^@\n]+)\s*@\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)/g;
  
  let match;
  let index = 0;
  while ((match = regex.exec(analysis)) !== null) {
    const label = match[1].trim().replace(/^["']|["']$/g, ''); // Remove surrounding quotes if any
    const x = parseInt(match[2], 10);
    const y = parseInt(match[3], 10);
    
    if (!isNaN(x) && !isNaN(y)) {
      elements.push({
        id: `element-${index}-${x}-${y}`,
        label,
        x,
        y
      });
      index++;
    }
  }
  
  return elements;
}

type Props = {
  analysis: string | null;
  containerRef: React.RefObject<HTMLDivElement | null>;
};

export function VisionOverlay({ analysis, containerRef }: Props) {
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  const elements = useMemo(() => {
    return parseVisionElements(analysis || "");
  }, [analysis]);

  // Track the actual size of the iframe container to scale coordinates
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateDimensions = () => {
      const rect = container.getBoundingClientRect();
      setDimensions({ width: rect.width, height: rect.height });
    };

    updateDimensions();

    const observer = new ResizeObserver(updateDimensions);
    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [containerRef]);

  if (elements.length === 0 || dimensions.width === 0) return null;

  const scaleX = dimensions.width / NATIVE_WIDTH;
  const scaleY = dimensions.height / NATIVE_HEIGHT;

  return (
    <div className="absolute inset-0 pointer-events-none z-50 overflow-hidden">
      <AnimatePresence>
        {elements.map((el, i) => {
          // Calculate scaled position
          const scaledX = el.x * scaleX;
          const scaledY = el.y * scaleY;
          
          // Approximate box size (since backend only gives center points)
          const boxWidth = 100 * scaleX; 
          const boxHeight = 32 * scaleY;

          return (
            <motion.div
              key={el.id}
              initial={{ opacity: 0, scale: 1.5, borderColor: "rgba(6, 182, 212, 0)" }}
              animate={{ opacity: 1, scale: 1, borderColor: "rgba(6, 182, 212, 0.8)" }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ 
                duration: 0.4, 
                delay: i * 0.05, // Stagger effect
                ease: "easeOut" 
              }}
              className="absolute border-2 border-cyan-500 rounded-sm shadow-[0_0_10px_rgba(6,182,212,0.5)] flex items-start justify-start"
              style={{
                left: Math.max(0, scaledX - boxWidth / 2),
                top: Math.max(0, scaledY - boxHeight / 2),
                width: boxWidth,
                height: boxHeight,
              }}
            >
              {/* Crosshair center dot */}
              <div className="absolute top-1/2 left-1/2 w-1.5 h-1.5 bg-cyan-400 rounded-full -translate-x-1/2 -translate-y-1/2 shadow-[0_0_5px_rgba(34,211,238,1)]" />
              
              {/* Label */}
              <motion.span 
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: (i * 0.05) + 0.2 }}
                className="absolute -top-6 left-0 bg-cyan-950/80 backdrop-blur-sm text-cyan-400 text-[10px] font-bold px-1.5 py-0.5 rounded border border-cyan-500/50 whitespace-nowrap"
              >
                {el.label}
              </motion.span>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
