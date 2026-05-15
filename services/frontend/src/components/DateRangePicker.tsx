import { useState } from 'react';
import { DayPicker, type DateRange } from 'react-day-picker';
import { ru } from 'date-fns/locale';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import 'react-day-picker/style.css';

export interface DateRangeValue {
  from?: Date;
  to?: Date;
}

interface Props {
  value: DateRangeValue;
  onChange: (v: DateRangeValue) => void;
  placeholder?: string;
  align?: 'start' | 'center' | 'end';
  className?: string;
  size?: 'sm' | 'default';
}

function fmt(d: Date | undefined): string {
  if (!d) return '';
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(d);
}

export function DateRangePicker({ value, onChange, placeholder = 'Выберите период', align = 'end', className, size = 'default' }: Props) {
  const [open, setOpen] = useState(false);
  const label = value.from
    ? value.to
      ? `${fmt(value.from)} — ${fmt(value.to)}`
      : `с ${fmt(value.from)}`
    : placeholder;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size={size === 'sm' ? 'sm' : 'default'} className={className}>
          <CalendarIcon className="h-3.5 w-3.5" />
          <span className="text-xs">{label}</span>
          {(value.from || value.to) && (
            <span
              role="button"
              tabIndex={0}
              className="ml-1 rounded-sm p-0.5 opacity-60 hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onChange({});
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  e.stopPropagation();
                  onChange({});
                }
              }}
            >
              <X className="h-3 w-3" />
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align={align} className="w-auto p-2">
        <DayPicker
          mode="range"
          locale={ru}
          weekStartsOn={1}
          numberOfMonths={2}
          selected={value as DateRange}
          onSelect={(range) => onChange({ from: range?.from, to: range?.to })}
        />
        <div className="flex justify-end gap-2 border-t pt-2">
          <Button variant="ghost" size="sm" onClick={() => onChange({})}>
            Очистить
          </Button>
          <Button size="sm" onClick={() => setOpen(false)}>
            Готово
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
