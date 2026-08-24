/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo } from "react";
import {
  InlineCitation,
  InlineCitationCard,
  InlineCitationCardBody,
  InlineCitationCardTrigger,
  InlineCitationCarousel,
  InlineCitationCarouselContent,
  InlineCitationCarouselHeader,
  InlineCitationCarouselIndex,
  InlineCitationCarouselItem,
  InlineCitationCarouselNext,
  InlineCitationCarouselPrev,
  InlineCitationSource,
  InlineCitationText,
} from "@/components/ai-elements/inline-citation";
import type { CiteRef } from "@/components/agent-ui/inline-citations";
import { cx } from "@/utils/cx";

type Props = {
  /** Source this pill represents (carousel starts here). */
  active: CiteRef;
  /** Full turn source list for the hover carousel. */
  sources: CiteRef[];
  /** Optional quoted / highlighted text before the pill. */
  quotedText?: string;
  className?: string;
};

/**
 * AI Elements Inline Citation wrapper — hoverable host pill + source carousel.
 */
export function CitationInline({
  active,
  sources,
  quotedText,
  className,
}: Props) {
  const ordered = useMemo(() => {
    if (sources.length === 0) return [active];
    const rest = sources.filter((s) => s.url !== active.url);
    const head = sources.find((s) => s.url === active.url) ?? active;
    return [head, ...rest];
  }, [active, sources]);

  const urls = useMemo(() => ordered.map((s) => s.url), [ordered]);

  return (
    <InlineCitation className={cx("align-middle", className)}>
      {quotedText ? (
        <InlineCitationText>{quotedText}</InlineCitationText>
      ) : null}
      <InlineCitationCard>
        <InlineCitationCardTrigger
          sources={urls}
          className="ml-0.5 mr-0.5 h-[18px] translate-y-[-1px] rounded-[5px] bg-background-secondary-default px-1.5 font-mono text-[10.5px] text-text-secondary shadow-card hover:bg-background-secondary-hover hover:text-text-primary"
        />
        <InlineCitationCardBody className="w-80 border border-separator-border bg-background-primary-default p-0 shadow-card">
          <InlineCitationCarousel>
            <InlineCitationCarouselHeader className="bg-background-secondary-default">
              <InlineCitationCarouselPrev />
              <InlineCitationCarouselIndex className="text-text-tertiary" />
              <InlineCitationCarouselNext />
            </InlineCitationCarouselHeader>
            <InlineCitationCarouselContent>
              {ordered.map((ref) => (
                <InlineCitationCarouselItem key={ref.url}>
                  <InlineCitationSource
                    title={ref.label}
                    url={ref.url}
                    description={ref.description}
                  />
                </InlineCitationCarouselItem>
              ))}
            </InlineCitationCarouselContent>
          </InlineCitationCarousel>
        </InlineCitationCardBody>
      </InlineCitationCard>
    </InlineCitation>
  );
}
