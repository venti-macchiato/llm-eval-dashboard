export function ChipFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const all = selected.size === 0;

  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(next);
  };

  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="chips">
        <button
          type="button"
          className={"chip" + (all ? " on" : "")}
          onClick={() => onChange(new Set())}
        >
          All
        </button>
        {options.map((option) => (
          <button
            type="button"
            key={option}
            className={"chip" + (!all && selected.has(option) ? " on" : "")}
            onClick={() => toggle(option)}
            title={option}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
