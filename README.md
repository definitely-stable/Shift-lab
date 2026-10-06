# Shift-lab · Delsk

Исследовательская лаборатория **Delsk**: компактное детерминированное представление данных для выбора базы, которая даёт выгодный delta patch для заданного target и кодера.

**Статус на 2026-10-06:** oracle G1 PASS; два screening (DELSK-004 Slice A, DELSK-002 X0) не нашли headroom для compact descriptor, поэтому программа перешла к [простому selector](.work/selector/README.md) ([решение](.work/decisions/2026-10-06-pivot-simple-selector.md)): метаданные (путь, линия релизов) плюс 64 B MinHash, K = 2. Его оценка in-sample; публичный API и wire format не утверждены.

Начать с [`.work/README.md`](.work/README.md): проверка двух исходных отчётов, обзор первичных источников, гипотезы, протокол oracle, корпус, план GitHub Actions и очередь issues.

Тесты и исследовательские измерения выполняются в **GitHub Actions**. Первый workflow проверяет целостность документации; измерительные workflow предстоит реализовать по исследовательским issues. Прохождение проверки документов ничего не говорит о качестве Delsk.

Текущая лицензия репозитория — [Apache-2.0](LICENSE). Лицензии внешних кодеков, baseline implementations и корпусов проверяются отдельно.
