import { useId, useRef, useState, type ReactNode } from "react";

type Section = { id: string; label: string; content: ReactNode };

/** Keep panels mounted so switching sections never discards draft inputs. */
export function SectionTabs({ label, sections, initial }: { label: string; sections: Section[]; initial?: string }) {
  const prefix = useId();
  const [active, setActive] = useState(initial || sections[0]?.id);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const current = sections.some(section => section.id === active) ? active : sections[0]?.id;
  return <div className="section-tabs">
    <div className="section-tablist" role="tablist" aria-label={label}>
      {sections.map((section, index) => <button
        key={section.id} ref={node => { buttons.current[index] = node; }}
        type="button" role="tab" id={`${prefix}-tab-${section.id}`}
        aria-controls={`${prefix}-panel-${section.id}`} aria-selected={current === section.id}
        tabIndex={current === section.id ? 0 : -1}
        onClick={() => setActive(section.id)}
        onKeyDown={event => {
          let next = index;
          if (event.key === "ArrowRight") next = (index + 1) % sections.length;
          else if (event.key === "ArrowLeft") next = (index + sections.length - 1) % sections.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = sections.length - 1;
          else return;
          event.preventDefault();
          setActive(sections[next].id);
          buttons.current[next]?.focus();
        }}
      >{section.label}</button>)}
    </div>
    {sections.map(section => <div key={section.id} role="tabpanel" tabIndex={0}
      id={`${prefix}-panel-${section.id}`} aria-labelledby={`${prefix}-tab-${section.id}`}
      hidden={current !== section.id}>{section.content}</div>)}
  </div>;
}
