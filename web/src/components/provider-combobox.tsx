import { Check, ChevronsUpDown } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

interface ProviderComboboxProps {
  value: string
  onChange: (value: string) => void
  options: string[]
  placeholder?: string
  emptyText?: string
  disabled?: boolean
}

export function ProviderCombobox({
  value,
  onChange,
  options,
  placeholder,
  emptyText,
  disabled,
}: ProviderComboboxProps): React.JSX.Element {
  const { t } = useTranslation()
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")

  const showCustomOption = search.length > 0 && !options.includes(search)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            "w-full justify-between font-normal",
            !value && "text-muted-foreground",
          )}
        >
          <span className="truncate">{value || (placeholder ?? t("combobox.selectPlaceholder"))}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput
            placeholder={t("combobox.searchPlaceholder")}
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>{emptyText ?? t("combobox.empty")}</CommandEmpty>
            {showCustomOption && (
              <CommandGroup heading={t("combobox.customHeading")}>
                <CommandItem
                  value={`__custom__:${search}`}
                  onSelect={() => {
                    onChange(search)
                    setSearch("")
                    setOpen(false)
                  }}
                >
                  <span className="italic text-muted-foreground mr-2">{t("combobox.useValue")}</span>
                  <span className="font-medium">{search}</span>
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {options.map((opt) => (
                <CommandItem
                  key={opt}
                  value={opt}
                  onSelect={() => {
                    onChange(opt)
                    setSearch("")
                    setOpen(false)
                  }}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === opt ? "opacity-100" : "opacity-0",
                    )}
                  />
                  {opt}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
